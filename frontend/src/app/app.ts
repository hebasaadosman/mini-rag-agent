import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { apiUrl } from './api-url';

interface Principal {
  subject: string;
  roles: string[];
  kind?: 'user' | 'demo';
  demo_project_id?: number | null;
}

interface DemoSessionResponse extends Principal {
  kind: 'demo';
  demo_project_id: number;
  suggested_questions: string[];
}

interface DemoProject {
  project_id: number;
  role: 'viewer';
}

interface AgentResponse {
  status: string;
  answer: string | null;
  clarification: { question?: string; options?: string[] } | null;
  error: string | null;
  sources?: Array<{ asset_name?: string | null; chunk_id?: number | null; score?: number | null }>;
}

interface PendingInteraction {
  question: string;
  options: string[];
  status: string;
}

interface SpeechStatus {
  enabled: boolean;
}

interface TranscriptionResponse {
  text: string;
}

const DEMO_PROJECT_STORAGE_KEY = 'mini-rag-demo-project';
const DEMO_THREAD_STORAGE_PREFIX = 'mini-rag-demo-thread:';

@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App implements OnInit {
  private readonly http = inject(HttpClient);

  protected readonly principal = signal<Principal | null>(null);
  protected readonly currentProject = signal<DemoProject | null>(null);
  protected readonly suggestedQuestions = signal<string[]>([]);
  protected readonly chatMessage = signal('');
  protected readonly chatAnswer = signal<string | null>(null);
  protected readonly chatSources = signal<AgentResponse['sources']>([]);
  protected readonly pendingInteraction = signal<PendingInteraction | null>(null);
  protected readonly resumeResponse = signal('');
  protected readonly threadId = signal<string | null>(null);
  protected readonly isLoading = signal(false);
  protected readonly isSpeaking = signal(false);
  protected readonly isRecording = signal(false);
  protected readonly voiceEnabled = signal(false);
  protected readonly message = signal('يمكن بدء جلسة Demo لتجربة الـworkspace الجاهز.');
  protected readonly messageTone = signal<'neutral' | 'success' | 'error'>('neutral');
  protected readonly isDemo = computed(() => this.principal()?.kind === 'demo');
  private recorder: MediaRecorder | null = null;
  private recordingStream: MediaStream | null = null;
  private recordingChunks: Blob[] = [];
  private recordingTimeout: number | null = null;

  async ngOnInit(): Promise<void> {
    await this.restoreSession();
  }

  protected startSingleSignOn(): void {
    window.location.assign(apiUrl('/api/v1/auth/login'));
  }

  protected async exploreDemo(): Promise<void> {
    this.isLoading.set(true);
    this.clearDemoState();
    try {
      const demo = await firstValueFrom(
        this.http.post<DemoSessionResponse>(apiUrl('/api/v1/auth/demo'), null),
      );
      this.principal.set(demo);
      this.suggestedQuestions.set(demo.suggested_questions);
      this.activateDemoProject(demo.demo_project_id);
      this.setMessage(
        'الـDemo workspace جاهز. يمكن اختيار سؤال مقترح أو إدخال سؤال جديد.',
        'success',
      );
    } catch {
      this.setMessage('تعذر بدء جلسة الـDemo. يرجى المحاولة مرة أخرى.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected chooseSuggestedQuestion(question: string): void {
    this.chatMessage.set(question);
  }
  protected updateChatMessage(value: string): void {
    this.chatMessage.set(value);
  }
  protected updateResumeResponse(value: string): void {
    this.resumeResponse.set(value);
  }

  protected async sendChat(): Promise<void> {
    const project = this.currentProject();
    const message = this.chatMessage().trim();
    if (!this.isDemo() || !project || !message || this.pendingInteraction()) {
      this.setMessage('يلزم بدء Demo session وإدخال سؤال أولًا.', 'error');
      return;
    }
    const threadId =
      this.threadId() ?? this.restoreThreadId(project.project_id) ?? crypto.randomUUID();
    this.threadId.set(threadId);
    sessionStorage.setItem(this.threadStorageKey(project.project_id), threadId);
    this.isLoading.set(true);
    this.chatAnswer.set(null);
    this.chatSources.set([]);
    try {
      const response = await firstValueFrom(
        this.http.post<AgentResponse>(apiUrl(`/api/v1/agents/${project.project_id}/chat`), {
          message,
          thread_id: threadId,
        }),
      );
      this.applyAgentResponse(response);
    } catch {
      this.setMessage('تعذر تنفيذ الـchat. يرجى المحاولة مرة أخرى.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected async resumeChat(option?: string): Promise<void> {
    const project = this.currentProject();
    const threadId = this.threadId();
    const response = (option ?? this.resumeResponse()).trim();
    if (!this.isDemo() || !project || !threadId || !response) {
      this.setMessage('يلزم إدخال رد أو اختيار أحد الخيارات للمتابعة.', 'error');
      return;
    }
    this.isLoading.set(true);
    try {
      const result = await firstValueFrom(
        this.http.post<AgentResponse>(apiUrl(`/api/v1/agents/${project.project_id}/chat/resume`), {
          response,
          thread_id: threadId,
        }),
      );
      this.resumeResponse.set('');
      this.applyAgentResponse(result);
    } catch {
      this.setMessage('تعذر استكمال الـtask. يرجى المحاولة مرة أخرى.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected async signOut(): Promise<void> {
    this.isLoading.set(true);
    this.clearDemoState();
    try {
      await firstValueFrom(this.http.post<void>(apiUrl('/api/v1/auth/logout'), null));
      this.setMessage('تم تسجيل الخروج وإلغاء جلسة الـDemo.', 'success');
    } catch {
      this.setMessage('تعذر تسجيل الخروج. أزيلت حالة المتصفح المحلية.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  private async restoreSession(): Promise<void> {
    this.isLoading.set(true);
    try {
      const principal = await firstValueFrom(this.http.get<Principal>(apiUrl('/api/v1/auth/me')));
      this.principal.set(principal);
      if (principal.kind === 'demo' && principal.demo_project_id) {
        this.activateDemoProject(principal.demo_project_id);
        this.setMessage('تمت استعادة جلسة الـDemo.', 'success');
      } else {
        this.setMessage('هذه الواجهة مخصصة لتجربة الـDemo العامة.', 'neutral');
      }
    } catch (error) {
      this.principal.set(null);
      this.clearDemoState();
      if (error instanceof HttpErrorResponse && error.status === 401) {
        this.setMessage('يمكن بدء جلسة Demo لتجربة الـworkspace الجاهز.', 'neutral');
      } else {
        this.setMessage('تعذر الاتصال بخدمة الجلسات. يرجى المحاولة مرة أخرى.', 'error');
      }
    } finally {
      this.isLoading.set(false);
    }
  }

  private applyAgentResponse(response: AgentResponse): void {
    const interactionStatuses = new Set([
      'clarification_required',
      'switch_confirmation_required',
      'approval_required',
    ]);
    if (interactionStatuses.has(response.status)) {
      this.chatAnswer.set(null);
      this.chatSources.set([]);
      this.pendingInteraction.set({
        status: response.status,
        question: response.clarification?.question ?? 'يلزم ردك قبل المتابعة.',
        options: response.clarification?.options ?? [],
      });
      this.setMessage('يحتاج الـagent إلى توضيح منك قبل المتابعة.', 'neutral');
      return;
    }
    this.pendingInteraction.set(null);
    if (response.error) {
      this.chatAnswer.set('تعذر إكمال هذا الطلب الآن. يرجى إعادة المحاولة لاحقًا.');
      this.chatSources.set([]);
      this.setMessage('تعذر إكمال الطلب.', 'error');
      return;
    }
    this.chatAnswer.set(response.answer ?? 'لم يرجع الـagent إجابة قابلة للعرض.');
    this.chatSources.set(response.sources ?? []);
    this.setMessage('تمت الإجابة مع المصادر.', 'success');
  }

  protected async playAnswer(): Promise<void> {
    const project = this.currentProject();
    const answer = this.chatAnswer();
    if (!project || !answer || this.isSpeaking()) return;

    this.isSpeaking.set(true);
    try {
      const audio = await firstValueFrom(
        this.http.post(
          apiUrl(`/api/v1/agents/${project.project_id}/speech`),
          { text: answer },
          { responseType: 'blob' },
        ),
      );
      const audioUrl = URL.createObjectURL(audio);
      const player = new Audio(audioUrl);
      player.onended = () => {
        URL.revokeObjectURL(audioUrl);
        this.isSpeaking.set(false);
      };
      player.onerror = () => {
        URL.revokeObjectURL(audioUrl);
        this.isSpeaking.set(false);
        this.setMessage('تعذر تشغيل الصوت. يرجى المحاولة مرة أخرى.', 'error');
      };
      await player.play();
    } catch {
      this.isSpeaking.set(false);
      this.setMessage('ميزة الاستماع غير متاحة الآن. يرجى المحاولة لاحقًا.', 'error');
    }
  }

  protected async toggleQuestionRecording(): Promise<void> {
    if (this.isRecording()) {
      this.stopQuestionRecording();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      this.setMessage('التسجيل الصوتي غير مدعوم في هذا المتصفح.', 'error');
      return;
    }
    try {
      this.recordingStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = this.preferredRecordingMimeType();
      this.recordingChunks = [];
      this.recorder = mimeType
        ? new MediaRecorder(this.recordingStream, { mimeType })
        : new MediaRecorder(this.recordingStream);
      this.recorder.ondataavailable = (event) => {
        if (event.data.size) this.recordingChunks.push(event.data);
      };
      this.recorder.onstop = () => void this.transcribeRecording();
      this.recorder.start();
      this.isRecording.set(true);
      this.setMessage('جارٍ التسجيل… اضغطِي «إيقاف التسجيل» عند الانتهاء.', 'neutral');
      this.recordingTimeout = window.setTimeout(() => this.stopQuestionRecording(), 60_000);
    } catch {
      this.releaseRecordingResources();
      this.setMessage('تعذر الوصول إلى الميكروفون. راجعي إذن الميكروفون للمتصفح.', 'error');
    }
  }

  private stopQuestionRecording(): void {
    if (this.recorder?.state === 'recording') this.recorder.stop();
  }

  private async transcribeRecording(): Promise<void> {
    const project = this.currentProject();
    const recorder = this.recorder;
    const chunks = this.recordingChunks;
    this.releaseRecordingResources();
    if (!project || !recorder || !chunks.length) {
      this.setMessage('لم يُلتقط صوت كافٍ لتحويله إلى نص.', 'error');
      return;
    }

    this.isLoading.set(true);
    try {
      const type = recorder.mimeType || 'audio/webm';
      const extension = type.includes('mp4') ? 'm4a' : 'webm';
      const form = new FormData();
      form.append('audio', new Blob(chunks, { type }), `question.${extension}`);
      const response = await firstValueFrom(
        this.http.post<TranscriptionResponse>(
          apiUrl(`/api/v1/agents/${project.project_id}/speech/transcribe`),
          form,
        ),
      );
      this.chatMessage.set(response.text);
      this.setMessage('تم تحويل السؤال إلى نص. راجعيه ثم أرسليه.', 'success');
    } catch {
      this.setMessage('تعذر تحويل التسجيل إلى نص. حاولي مرة أخرى.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  private preferredRecordingMimeType(): string | undefined {
    return ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'].find((type) =>
      MediaRecorder.isTypeSupported(type),
    );
  }

  private releaseRecordingResources(): void {
    if (this.recordingTimeout !== null) window.clearTimeout(this.recordingTimeout);
    this.recordingTimeout = null;
    this.recordingStream?.getTracks().forEach((track) => track.stop());
    this.recordingStream = null;
    this.recorder = null;
    this.recordingChunks = [];
    this.isRecording.set(false);
  }

  private activateDemoProject(projectId: number): void {
    const project = { project_id: projectId, role: 'viewer' as const };
    this.currentProject.set(project);
    sessionStorage.setItem(DEMO_PROJECT_STORAGE_KEY, String(projectId));
    this.threadId.set(this.restoreThreadId(projectId));
    this.chatAnswer.set(null);
    this.chatSources.set([]);
    this.pendingInteraction.set(null);
    this.resumeResponse.set('');
    void this.refreshSpeechAvailability(projectId);
  }

  private async refreshSpeechAvailability(projectId: number): Promise<void> {
    try {
      const status = await firstValueFrom(
        this.http.get<SpeechStatus>(apiUrl(`/api/v1/agents/${projectId}/speech/status`)),
      );
      this.voiceEnabled.set(status.enabled);
    } catch {
      this.voiceEnabled.set(false);
    }
  }

  private clearDemoState(): void {
    this.principal.set(null);
    this.currentProject.set(null);
    this.suggestedQuestions.set([]);
    this.chatMessage.set('');
    this.chatAnswer.set(null);
    this.chatSources.set([]);
    this.pendingInteraction.set(null);
    this.resumeResponse.set('');
    this.threadId.set(null);
    this.isSpeaking.set(false);
    this.releaseRecordingResources();
    this.voiceEnabled.set(false);
    sessionStorage.removeItem(DEMO_PROJECT_STORAGE_KEY);
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(DEMO_THREAD_STORAGE_PREFIX)) sessionStorage.removeItem(key);
    }
  }

  private restoreThreadId(projectId: number): string | null {
    const threadId = sessionStorage.getItem(this.threadStorageKey(projectId));
    return threadId && /^[0-9a-f-]{36}$/i.test(threadId) ? threadId : null;
  }

  private threadStorageKey(projectId: number): string {
    return `${DEMO_THREAD_STORAGE_PREFIX}${projectId}`;
  }
  private setMessage(message: string, tone: 'neutral' | 'success' | 'error'): void {
    this.message.set(message);
    this.messageTone.set(tone);
  }
}
