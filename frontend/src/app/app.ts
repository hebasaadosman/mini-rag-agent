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
  protected readonly message = signal('ابدئي جلسة Demo لتجربة الـworkspace الجاهز.');
  protected readonly messageTone = signal<'neutral' | 'success' | 'error'>('neutral');
  protected readonly isDemo = computed(() => this.principal()?.kind === 'demo');

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
      const demo = await firstValueFrom(this.http.post<DemoSessionResponse>(apiUrl('/api/v1/auth/demo'), null));
      this.principal.set(demo);
      this.suggestedQuestions.set(demo.suggested_questions);
      this.activateDemoProject(demo.demo_project_id);
      this.setMessage('الـDemo workspace جاهز. اختاري سؤالًا مقترحًا أو اكتبي سؤالك.', 'success');
    } catch {
      this.setMessage('تعذر بدء جلسة الـDemo. حاولي مرة أخرى.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected chooseSuggestedQuestion(question: string): void { this.chatMessage.set(question); }
  protected updateChatMessage(value: string): void { this.chatMessage.set(value); }
  protected updateResumeResponse(value: string): void { this.resumeResponse.set(value); }

  protected async sendChat(): Promise<void> {
    const project = this.currentProject();
    const message = this.chatMessage().trim();
    if (!this.isDemo() || !project || !message || this.pendingInteraction()) {
      this.setMessage('ابدئي Demo session واكتبي سؤالًا أولًا.', 'error');
      return;
    }
    const threadId = this.threadId() ?? this.restoreThreadId(project.project_id) ?? crypto.randomUUID();
    this.threadId.set(threadId);
    sessionStorage.setItem(this.threadStorageKey(project.project_id), threadId);
    this.isLoading.set(true);
    this.chatAnswer.set(null);
    this.chatSources.set([]);
    try {
      const response = await firstValueFrom(this.http.post<AgentResponse>(apiUrl(`/api/v1/agents/${project.project_id}/chat`), { message, thread_id: threadId }));
      this.applyAgentResponse(response);
    } catch {
      this.setMessage('تعذر تنفيذ الـchat. حاولي مرة أخرى.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected async resumeChat(option?: string): Promise<void> {
    const project = this.currentProject();
    const threadId = this.threadId();
    const response = (option ?? this.resumeResponse()).trim();
    if (!this.isDemo() || !project || !threadId || !response) {
      this.setMessage('اكتبي ردًا أو اختاري أحد الخيارات للمتابعة.', 'error');
      return;
    }
    this.isLoading.set(true);
    try {
      const result = await firstValueFrom(this.http.post<AgentResponse>(apiUrl(`/api/v1/agents/${project.project_id}/chat/resume`), { response, thread_id: threadId }));
      this.resumeResponse.set('');
      this.applyAgentResponse(result);
    } catch {
      this.setMessage('تعذر استكمال الـtask. حاولي مرة أخرى.', 'error');
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
        this.setMessage('ابدئي جلسة Demo لتجربة الـworkspace الجاهز.', 'neutral');
      } else {
        this.setMessage('تعذر الاتصال بخدمة الجلسات. حاولي مرة أخرى.', 'error');
      }
    } finally {
      this.isLoading.set(false);
    }
  }

  private applyAgentResponse(response: AgentResponse): void {
    const interactionStatuses = new Set(['clarification_required', 'switch_confirmation_required', 'approval_required']);
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
    this.chatAnswer.set(response.answer ?? response.error ?? 'لم يرجع الـagent إجابة قابلة للعرض.');
    this.chatSources.set(response.sources ?? []);
    this.setMessage(response.error ? 'تعذر إكمال الطلب.' : 'تمت الإجابة مع المصادر.', response.error ? 'error' : 'success');
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

  private threadStorageKey(projectId: number): string { return `${DEMO_THREAD_STORAGE_PREFIX}${projectId}`; }
  private setMessage(message: string, tone: 'neutral' | 'success' | 'error'): void { this.message.set(message); this.messageTone.set(tone); }
}
