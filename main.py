import tkinter as tk
from RedManager import RedManager
from datetime import datetime, timedelta
from WindowsPowerMonitor import WindowsPowerMonitor
from TrayIcon import TrayIcon
import threading
from RegisterTimeDialog import RegisterTimeDialog
from ApiKeyConfig import get_redmine_config


class QuadroHorasNav:
    def __init__(self, root, red_manager):
        self.root = root
        self.red_manager = red_manager
        self.root.title("Gestor de Horas com Navegação")
        self.root.geometry("900x500")
        self.root.configure(bg="#f5f5f5")

        # Estado inicial: Segunda-feira da semana atual
        self.hoje_real = datetime.now().date()
        self.segunda_da_semana = self.get_segunda_feira(self.hoje_real)
        
        # Simulação de dados vindo de um banco (Indexado por Data ISO)
        self.horas_tarefas = {
            str(self.hoje_real): "02:45",
            str(self.hoje_real - timedelta(days=1)): "01:30"
        }

        self.traducao_dias = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        self.traducao_meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                               "agosto", "setembro", "outubro", "novembro", "dezembro"]

        # Dados da semana exibida (carregados do Redmine em carregar_dados)
        self.working_week_tasks = {}
        self.month_hours = None

        # Rastreamento de tarefas em andamento
        self.time_label_ref = None
        self.counted_time_label_ref = None
        self.suspended_task = None  # Tarefa que estava rodando antes da suspensão
        self.monitor = None
        self.tray = None
        self.is_closing = False
        self.root.protocol("WM_DELETE_WINDOW", self.close_application)
        
        self.setup_ui()
        self.start_update_timer()

    def get_segunda_feira(self, data):
        """Retorna a data da segunda-feira da semana da data fornecida."""
        return data - timedelta(days=data.weekday())

    def navegar_semana(self, semanas):
        """Navega para frente ou para trás no tempo."""
        self.segunda_da_semana += timedelta(weeks=semanas)
        self.carregar_dados()

    def carregar_dados(self, force=False):
        """Consulta a semana exibida e o total do mês no Redmine e redesenha o quadro.
        Sem conexão, usa o cache local e avisa no cabeçalho."""
        inicio = self.segunda_da_semana
        fim = self.segunda_da_semana + timedelta(days=7)
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            self.working_week_tasks = self.red_manager.get_working_week(inicio, fim, force=force)
            self.month_hours = self.red_manager.get_month_hours(self.hoje_real)
            self.lbl_aviso.config(text="")
        except Exception as e:
            print(f"Falha ao consultar o Redmine: {type(e).__name__}: {e}")
            self.working_week_tasks = self.red_manager.get_cached_week(inicio, fim)
            self.lbl_aviso.config(text="⚠ Sem conexão com o Redmine: exibindo dados do cache")
        finally:
            self.root.config(cursor="")

        self.atualizar_cabecalho()
        self.atualizar_quadro()

    def atualizar_cabecalho(self):
        """Atualiza nome do usuário e total de horas do mês."""
        self.lbl_usuario.config(text=f"👤 {self.red_manager.get_user_name()}")
        nome_mes = f"{self.traducao_meses[self.hoje_real.month - 1]}/{self.hoje_real.year}"
        total_mes = "—" if self.month_hours is None else self.formatar_horas(self.month_hours)
        self.lbl_total_mes.config(text=f"Horas em {nome_mes}: {total_mes}")

    def formatar_horas(self, horas):
        """Formata horas decimais como HH:MM (ex.: 1.5 -> 01:30)."""
        minutos = round(horas * 60)
        return f"{minutos // 60:02d}:{minutos % 60:02d}"
    
    def start_working_task(self, task_id):
        """Inicia o rastreamento de uma tarefa. Se houver tarefa em andamento, pausa primeiro."""
        if self.red_manager.working_task is not None and self.red_manager.working_task != task_id:
            self.pause_current_working_task()
        
        if task_id not in self.red_manager.current_working_tasks:
            self.red_manager.current_working_tasks[task_id] = {
                "start_time": datetime.now(),
                "elapsed_time": timedelta(0),
                "status": "running"
            }
        else:
            self.red_manager.current_working_tasks[task_id]["start_time"] = datetime.now()
            self.red_manager.current_working_tasks[task_id]["status"] = "running"
        
        self.red_manager.working_task = task_id
        self.atualizar_quadro()
        print(f"Iniciando tarefa {task_id}")
    
    def pause_current_working_task(self):
        """Pausa a tarefa atualmente em andamento e acumula o tempo decorrido."""
        if self.red_manager.working_task is None:
            return
        
        task_data = self.red_manager.current_working_tasks.get(self.red_manager.working_task)
        if task_data and task_data["status"] == "running":
            elapsed = datetime.now() - task_data["start_time"]
            task_data["elapsed_time"] += elapsed
            task_data["status"] = "idle"
            print(f"Pausando tarefa {self.red_manager.working_task}, tempo acumulado: {task_data['elapsed_time']}")
        
        self.red_manager.working_task = None
        self.atualizar_quadro()

    def stop_current_working_task(self, task_id=None):
        """Para uma tarefa e limpa o tempo contado localmente."""
        task_id = task_id if task_id is not None else self.red_manager.working_task
        if task_id is None:
            return

        task_data = self.red_manager.current_working_tasks.get(task_id)
        if task_data:
            task_data["elapsed_time"] = timedelta(0)
            task_data["status"] = "idle"
            task_data.pop("start_time", None)

        if self.red_manager.working_task == task_id:
            self.red_manager.working_task = None

    def _get_task_elapsed_time(self, task_id):
        task_data = self.red_manager.current_working_tasks.get(task_id)
        if task_data is None:
            return timedelta(0)

        elapsed_time = task_data.get("elapsed_time", timedelta(0))
        if task_data.get("status") == "running":
            elapsed_time += datetime.now() - task_data["start_time"]
        return elapsed_time

    def register_task_time(self, task_id):
        """Abre o diálogo e registra o tempo confirmado pelo usuário."""
        task_data = self.red_manager.current_working_tasks.get(task_id)
        if task_data is None:
            return

        elapsed_time = self._get_task_elapsed_time(task_id)
        activities = self.red_manager.get_time_entry_activities()
        task = self.red_manager.get_task_by_id(task_id)
        result = RegisterTimeDialog(
            self.root,
            elapsed_time,
            activities,
            task_id,
            task["desc"]
        ).show()

        if result is None:
            return

        hours = result["seconds"] / 3600
        self.red_manager.register_time_entry(
            task_id,
            hours,
            result["description"],
            result["activity_id"]
        )
        self.stop_current_working_task(task_id)
        # Recarrega do Redmine para refletir o lançamento no quadro e no total do mês
        self.carregar_dados()
    
    def _minimize_to_tray(self):
        """Minimiza a janela para a bandeja."""
        if self.tray:
            self.tray._hide_window()

    def close_application(self):
        """Encerra todos os componentes e fecha a aplicação."""
        if self.is_closing:
            return

        self.is_closing = True
        if self.tray:
            self.tray.stop()
        if self.monitor:
            self.monitor.stop()
        self.root.destroy()
    
    def clear_task_time(self, task_id):
        task = self.red_manager.current_working_tasks.get(task_id)
        if task is not None:
            task['elapsed_time'] = timedelta(0)
        self.atualizar_quadro()

    def pause_on_suspend(self):
        """Pausa a tarefa quando o Windows suspende e salva qual era a tarefa em andamento."""
        if self.red_manager.working_task is not None:
            self.suspended_task = self.red_manager.working_task
            self.pause_current_working_task()
            print(f"Windows suspendeu. Tarefa {self.suspended_task} foi pausada.")
    
    def resume_on_wake(self):
        """Retoma a tarefa que estava em andamento quando o Windows acordar."""
        if self.suspended_task is not None:
            self.start_working_task(self.suspended_task)
            self.suspended_task = None
            print(f"Windows acordou. Retomando tarefa anterior.")
        else:
            print("Windows acordou, mas não havia tarefa em andamento.")
    
    def update_time_label(self):
        """Atualiza o label de tempo a cada segundo se houver tarefa em andamento."""
        # Monitorar estado de suspensão do Windows
        if hasattr(self, 'monitor') and self.monitor is not None:
            if self.monitor.is_suspended and not hasattr(self, '_was_suspended'):
                # Windows foi suspenso agora
                self._was_suspended = True
                self.pause_on_suspend()
            elif not self.monitor.is_suspended and hasattr(self, '_was_suspended') and self._was_suspended:
                # Windows acordou
                self._was_suspended = False
                self.resume_on_wake()
        
        if self.time_label_ref is not None and self.red_manager.working_task is not None:
            task_data = self.red_manager.current_working_tasks.get(self.red_manager.working_task)
            if task_data:
                current_elapsed = None
                if task_data["status"] == "running":
                    current_elapsed = (datetime.now() - task_data["start_time"]) + task_data["elapsed_time"]
                elif task_data["status"] == "idle":
                    current_elapsed = task_data["elapsed_time"]
                
                if current_elapsed:
                    if task_data.get('registered_time'):
                        current_elapsed += task_data.get('registered_time')
                    valor_hora = str(current_elapsed).split('.')[0]
                    self.time_label_ref.config(text=valor_hora)
                    if self.counted_time_label_ref is not None:
                        counted_value = str(
                            self._get_task_elapsed_time(self.red_manager.working_task)
                        ).split('.')[0]
                        self.counted_time_label_ref.config(
                            text=f"Tempo contado: {counted_value}"
                        )
        
        self.root.after(1000, self.update_time_label)
    
    def start_update_timer(self):
        """Inicia a rotina de atualização de labels a cada segundo."""
        self.root.after(1000, self.update_time_label)
    
    def setup_tray_icon(self):
        """Configura o ícone de bandeja em uma thread separada."""
        self.tray = TrayIcon(self.root, self)
        tray_thread = threading.Thread(target=self.tray.run, daemon=True)
        tray_thread.start()

    def setup_ui(self):
        # --- PAINEL DE NAVEGAÇÃO (TOPO) ---
        self.topo_frame = tk.Frame(self.root, bg="#333", pady=10)
        self.topo_frame.pack(fill="x")

        btn_ant = tk.Button(self.topo_frame, text="◀ Semana Anterior", command=lambda: self.navegar_semana(-1),
                            bg="#555", fg="white", relief="flat", padx=10)
        btn_ant.pack(side="left", padx=20)

        self.lbl_periodo = tk.Label(self.topo_frame, text="", font=("Segoe UI", 11, "bold"), bg="#333", fg="white")
        self.lbl_periodo.pack(side="left", expand=True)

        btn_prox = tk.Button(self.topo_frame, text="Próxima Semana ▶", command=lambda: self.navegar_semana(1),
                             bg="#555", fg="white", relief="flat", padx=10)
        btn_prox.pack(side="right", padx=20)
        
        btn_minimize = tk.Button(self.topo_frame, text="🔽 Minimizar", command=self._minimize_to_tray,
                                 bg="#555", fg="white", relief="flat", padx=10)
        btn_minimize.pack(side="right", padx=5)

        # --- BARRA DE INFORMAÇÕES (usuário, total do mês, atualizar) ---
        self.info_frame = tk.Frame(self.root, bg="#444", pady=4)
        self.info_frame.pack(fill="x")

        self.lbl_usuario = tk.Label(self.info_frame, text="", font=("Segoe UI", 9, "bold"), bg="#444", fg="white")
        self.lbl_usuario.pack(side="left", padx=20)

        self.lbl_total_mes = tk.Label(self.info_frame, text="", font=("Segoe UI", 9), bg="#444", fg="white")
        self.lbl_total_mes.pack(side="left", padx=10)

        btn_refresh = tk.Button(self.info_frame, text="⟳ Atualizar", command=self.atualizar_do_redmine,
                                bg="#555", fg="white", relief="flat", padx=10)
        btn_refresh.pack(side="right", padx=20)

        self.lbl_aviso = tk.Label(self.info_frame, text="", font=("Segoe UI", 9, "bold"), bg="#444", fg="#ffc107")
        self.lbl_aviso.pack(side="right", padx=10)

        # --- CONTAINER DA TABELA (com barra de rolagem vertical) ---
        scroll_frame = tk.Frame(self.root, bg="#f5f5f5")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(scroll_frame, bg="#f5f5f5", highlightthickness=0)
        scrollbar = tk.Scrollbar(scroll_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.table_container = tk.Frame(self.canvas, bg="#f5f5f5")
        self.canvas.create_window((0, 0), window=self.table_container, anchor="nw")
        self.table_container.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        # Roda do mouse só enquanto o ponteiro está sobre a tabela
        self.canvas.bind("<Enter>", lambda event: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda event: self.canvas.unbind_all("<MouseWheel>"))

        self.carregar_dados()

    def _on_mousewheel(self, event):
        # Só rola se o conteúdo for maior que a área visível
        if self.table_container.winfo_height() > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def atualizar_do_redmine(self):
        """Botão Atualizar: força nova consulta ao Redmine, ignorando o cache."""
        self.carregar_dados(force=True)

    def atualizar_quadro(self):
        # Limpa a tabela atual para redesenhar
        for widget in self.table_container.winfo_children():
            widget.destroy()
        # As labels antigas foram destruídas; são recriadas abaixo se a tarefa em andamento estiver na semana
        self.time_label_ref = None
        self.counted_time_label_ref = None

        domingo = self.segunda_da_semana + timedelta(days=6)
        self.lbl_periodo.config(text=f"Período: {self.segunda_da_semana.strftime('%d/%m')} até {domingo.strftime('%d/%m/%Y')}")

        # --- CABEÇALHO ---
        tk.Label(self.table_container, text="Tarefa (ID / Desc / Status)", font=("Segoe UI", 10, "bold"), 
                 bg="#e0e0e0", borderwidth=1, relief="solid").grid(row=0, column=0, sticky="nsew")

        for i in range(7):
            data_dia = self.segunda_da_semana + timedelta(days=i)
            is_hoje = data_dia == self.hoje_real
            
            cor_bg = "#0078d7" if is_hoje else "#e0e0e0"
            cor_fg = "white" if is_hoje else "black"
            
            texto_cabecalho = f"{self.traducao_dias[i]}\n{data_dia.strftime('%d/%m')}"
            
            lbl = tk.Label(self.table_container, text=texto_cabecalho, font=("Segoe UI", 9, "bold"),
                           bg=cor_bg, fg=cor_fg, borderwidth=1, relief="solid", width=12, pady=5)
            lbl.grid(row=0, column=i+1, sticky="nsew")

        working_week_tasks = self.working_week_tasks
        index = 1
        for t, working_days in working_week_tasks.items():
            task = self.red_manager.get_task_by_id(t)
            print(t, working_days)
            self.renderizar_linha_tarefa(index, task, working_days)
            index += 1
        self.red_manager.save_to_file()

        self.renderizar_linha_totais(index, working_week_tasks)

    def renderizar_linha_totais(self, row, working_week_tasks):
        """Linha final com o total de horas registradas no Redmine em cada dia."""
        tk.Label(self.table_container, text="Total do dia", font=("Segoe UI", 9, "bold"),
                 bg="#e0e0e0", borderwidth=1, relief="solid", anchor="w", padx=8, pady=4
                 ).grid(row=row, column=0, sticky="nsew")

        for i in range(7):
            data_str = str(self.segunda_da_semana + timedelta(days=i))
            total = sum(working_days.get(data_str, 0) for working_days in working_week_tasks.values())
            is_hoje = (self.segunda_da_semana + timedelta(days=i)) == self.hoje_real
            tk.Label(self.table_container, text=self.formatar_horas(total), font=("Segoe UI", 10, "bold"),
                     bg="#e3f2fd" if is_hoje else "#e0e0e0", borderwidth=1, relief="solid", pady=4
                     ).grid(row=row, column=i+1, sticky="nsew")

    def renderizar_linha_tarefa(self, row, info, horas_tarefas):
        # --- Painel Lateral (ID, Descrição, Status) ---
        # Definindo cores baseadas no status
        cor_status = "#28a745" if info['status'].lower() == "concluído" else "#0078d7"
        
        f_task = tk.Frame(self.table_container, bd=1, relief="solid", bg="white", padx=8, pady=5)
        f_task.grid(row=row, column=0, sticky="nsew")
        
        # ID da Tarefa
        tk.Label(f_task, text=f"ID {info['id']}", font=("Consolas", 8, "bold"), 
                 bg="white", fg="#777").pack(anchor="w")
        
        # Descrição (com quebra de linha se for muito grande)
        tk.Label(f_task, text=info['desc'], font=("Segoe UI", 9, "bold"), 
                 bg="white", wraplength=150, justify="left").pack(anchor="w", pady=(2, 5))
        
        # Status (Agora visível e estilizado)
        lbl_status = tk.Label(f_task, text=info['status'].upper(), font=("Segoe UI", 7, "bold"), 
                              bg="#f0f0f0", fg=cor_status, padx=4, pady=1)
        lbl_status.pack(anchor="w")

        # --- Restante das Células de Dias (Horas) ---
        for i in range(7):
            data_dia = self.segunda_da_semana + timedelta(days=i)
            data_str = str(data_dia)
            valor_hora = str(timedelta(hours=horas_tarefas.get(data_str, 0)))
            
            if data_dia == self.hoje_real:
                tempo_base = timedelta(hours=horas_tarefas.get(data_str, 0))
                tempo_contado = self._get_task_elapsed_time(info['id'])

                # Se a tarefa está em current_working_tasks, somar o tempo acumulado
                if info['id'] in self.red_manager.current_working_tasks:
                    task_data = self.red_manager.current_working_tasks[info['id']]
                    #guarda as horas registradas do redmine
                    task_data['registered_time'] = tempo_base
                    valor_hora = str(tempo_base + tempo_contado).split('.')[0]
                
                celula = tk.Frame(self.table_container, bg="#e3f2fd", bd=1, relief="solid")
                celula.grid(row=row, column=i+1, sticky="nsew")
                lbl_hora = tk.Label(celula, text=valor_hora, font=("Segoe UI", 10, "bold"), bg="#e3f2fd")
                lbl_hora.pack(pady=2)
                
                # Se esta tarefa está em andamento, guarda a referência do label
                if info['id'] == self.red_manager.working_task:
                    self.time_label_ref = lbl_hora
                
                f_btns = tk.Frame(celula, bg="#e3f2fd")
                f_btns.pack()
                
                # Determina qual botão mostrar baseado no status
                is_working = (info['id'] == self.red_manager.working_task)
                has_local_time = (
                    info['id'] in self.red_manager.current_working_tasks
                    and self._get_task_elapsed_time(info['id']) > timedelta(0)
                )
                
                if is_working:
                    tk.Button(f_btns, text="⏸", font=("Arial", 7), bg="#f8d7da", width=3, relief="groove",
                              command=self.pause_current_working_task).pack(side="left", padx=1)
                else:
                    tk.Button(f_btns, text="▶", font=("Arial", 7), bg="#d4edda", width=3, relief="groove",
                              command=lambda: self.start_working_task(info['id'])).pack(side="left", padx=1)
                
                tk.Button(f_btns, text="❌", font=("Arial", 7), bg="#d4edda", width=3, relief="groove",
                              command=lambda: self.clear_task_time(info['id'])).pack(side="left", padx=1)
                if is_working or has_local_time:
                    tk.Button(f_btns, text="⏱", font=("Arial", 7), bg="#d9edf7", width=3, relief="groove",
                              command=lambda: self.register_task_time(info['id'])).pack(side="left", padx=1)

                tk.Label(
                    celula,
                    text=f"Tempo registrado: {str(tempo_base).split('.')[0]}",
                    font=("Segoe UI", 8),
                    bg="#e3f2fd",
                    fg="#198754"
                ).pack(anchor="w", padx=4, pady=(3, 0))
                tk.Label(
                    celula,
                    text=f"Tempo contado: {str(tempo_contado).split('.')[0]}",
                    font=("Segoe UI", 8),
                    bg="#e3f2fd",
                    fg="#0078d7"
                ).pack(anchor="w", padx=4)
                if is_working:
                    self.counted_time_label_ref = celula.winfo_children()[-1]
            else:
                lbl = tk.Label(self.table_container, text=valor_hora, bg="white", 
                               borderwidth=1, relief="solid", font=("Segoe UI", 10))
                lbl.grid(row=row, column=i+1, sticky="nsew")


if __name__ == "__main__":
    root = tk.Tk()
    # Mantém a janela principal oculta até ter URL e chave de API válidas
    root.withdraw()
    config = get_redmine_config(root)
    if config is None:
        root.destroy()
        raise SystemExit(0)

    redmine_url, api_key = config
    red_manager = RedManager(redmine_url, key=api_key)
    root.deiconify()
    app = QuadroHorasNav(root, red_manager)
    
    monitor = WindowsPowerMonitor(root)
    app.monitor = monitor
    
    # Configurar ícone de bandeja
    app.setup_tray_icon()
    
    root.mainloop()