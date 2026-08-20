import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { firstValueFrom } from 'rxjs';

interface Principal {
  subject: string;
  roles: string[];
}

interface ProjectResponse {
  project_id: number;
  role: string;
}

@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  private readonly http = inject(HttpClient);

  protected readonly token = signal(sessionStorage.getItem('mini-rag-dev-token') ?? '');
  protected readonly projectDescription = signal('');
  protected readonly principal = signal<Principal | null>(null);
  protected readonly currentProject = signal<ProjectResponse | null>(null);
  protected readonly isLoading = signal(false);
  protected readonly message = signal('أدخلي access token مؤقتًا ثم تحققي من الهوية.');
  protected readonly messageTone = signal<'neutral' | 'success' | 'error'>('neutral');
  protected readonly isAuthenticated = computed(() => this.principal() !== null);

  protected updateToken(value: string): void {
    this.token.set(value.trim());
    this.principal.set(null);
    this.currentProject.set(null);

    if (value.trim()) {
      sessionStorage.setItem('mini-rag-dev-token', value.trim());
    } else {
      sessionStorage.removeItem('mini-rag-dev-token');
    }
  }

  protected updateProjectDescription(value: string): void {
    this.projectDescription.set(value);
  }

  protected async verifyIdentity(): Promise<void> {
    if (!this.token()) {
      this.setMessage('أدخلي bearer token أولًا.', 'error');
      return;
    }

    this.isLoading.set(true);
    try {
      const principal = await firstValueFrom(
        this.http.get<Principal>('/api/v1/auth/me', { headers: this.authHeaders() }),
      );
      this.principal.set(principal);
      this.setMessage(`تم التحقق: ${principal.subject}`, 'success');
    } catch {
      this.principal.set(null);
      this.setMessage('تعذر التحقق من الـtoken. تأكدي من صلاحيته ومن تشغيل الـAPI.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  protected async createProject(): Promise<void> {
    if (!this.isAuthenticated()) {
      this.setMessage('تحققي من الهوية قبل إنشاء Project.', 'error');
      return;
    }

    this.isLoading.set(true);
    try {
      const project = await firstValueFrom(
        this.http.post<ProjectResponse>(
          '/api/v1/projects',
          { description: this.projectDescription().trim() || null },
          { headers: this.authHeaders() },
        ),
      );
      this.currentProject.set(project);
      this.setMessage(`تم إنشاء Project #${project.project_id} بدور ${project.role}.`, 'success');
    } catch {
      this.setMessage('تعذر إنشاء الـProject. راجعي الـAPI logs وصلاحيات الـtoken.', 'error');
    } finally {
      this.isLoading.set(false);
    }
  }

  private authHeaders(): HttpHeaders {
    return new HttpHeaders({ Authorization: `Bearer ${this.token()}` });
  }

  private setMessage(message: string, tone: 'neutral' | 'success' | 'error'): void {
    this.message.set(message);
    this.messageTone.set(tone);
  }
}
