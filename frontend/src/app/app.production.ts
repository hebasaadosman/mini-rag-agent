import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { firstValueFrom } from 'rxjs';

interface Principal { subject: string; roles: string[]; }
interface ProjectResponse { project_id: number; role: string; }

@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.production.html',
})
export class App implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly projectDescription = signal('');
  protected readonly principal = signal<Principal | null>(null);
  protected readonly currentProject = signal<ProjectResponse | null>(null);
  protected readonly isLoading = signal(false);
  protected readonly message = signal('سجّلي الدخول عبر نظام الهوية المؤسسي.');
  protected readonly messageTone = signal<'neutral' | 'success' | 'error'>('neutral');
  protected readonly isAuthenticated = computed(() => this.principal() !== null);

  async ngOnInit(): Promise<void> { await this.verifyIdentity(); }
  protected updateProjectDescription(value: string): void { this.projectDescription.set(value); }
  protected startSingleSignOn(): void { window.location.assign('/api/v1/auth/login'); }

  protected async verifyIdentity(): Promise<void> {
    this.isLoading.set(true);
    try {
      const principal = await firstValueFrom(this.http.get<Principal>('/api/v1/auth/me'));
      this.principal.set(principal);
      this.setMessage(`تم التحقق: ${principal.subject}`, 'success');
    } catch {
      this.principal.set(null);
      this.setMessage('سجّلي الدخول عبر نظام الهوية المؤسسي.', 'neutral');
    } finally { this.isLoading.set(false); }
  }

  protected async createProject(): Promise<void> {
    if (!this.isAuthenticated()) { this.setMessage('يجب التحقق من الهوية قبل إنشاء Project.', 'error'); return; }
    this.isLoading.set(true);
    try {
      const project = await firstValueFrom(this.http.post<ProjectResponse>(
        '/api/v1/projects', { description: this.projectDescription().trim() || null }, { headers: this.csrfHeaders() },
      ));
      this.currentProject.set(project);
      this.setMessage(`تم إنشاء Project #${project.project_id} بدور ${project.role}.`, 'success');
    } catch { this.setMessage('تعذر إنشاء الـProject. راجعي الصلاحيات أو الـAPI logs.', 'error'); }
    finally { this.isLoading.set(false); }
  }

  private csrfHeaders(): HttpHeaders {
    const csrfToken = document.cookie.split('; ').find((cookie) => cookie.startsWith('mini_rag_csrf='))?.split('=')[1];
    return csrfToken ? new HttpHeaders({ 'X-CSRF-Token': decodeURIComponent(csrfToken) }) : new HttpHeaders();
  }
  private setMessage(message: string, tone: 'neutral' | 'success' | 'error'): void {
    this.message.set(message); this.messageTone.set(tone);
  }
}
