from redminelib import Redmine
from redminelib.resources import User
from datetime import date, timedelta
import pickle
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class RedManager:
    def __init__(self, url, key):
        # 1. Instancia o cliente Redmine
        self.redmine = Redmine(url, key=key)

        # 2. Configura a estratégia de retry
        retry_strategy = Retry(
            total=3,                       # Número de tentativas
            backoff_factor=1,              # Espera 1s, 2s, 4s entre tentativas
            status_forcelist=[500, 502, 503, 504],
            raise_on_status=False
        )

        # 3. Cria o adaptador HTTP
        adapter = HTTPAdapter(max_retries=retry_strategy)

        # 4. Aplica o adaptador na sessão interna da biblioteca
        self.redmine.engine.session.mount("http://", adapter)
        self.redmine.engine.session.mount("https://", adapter)


        self.me = None
        self.tasks_by_id = None
        self.week_cache = None
        self.working_task = None
        self.current_working_tasks = None
        self.load_from_file()
        if self.tasks_by_id is None: self.tasks_by_id = {}
        if self.week_cache is None: self.week_cache = {} 
        if self.current_working_tasks is None: self.current_working_tasks = {}
        if self.me is None: self.me = self.redmine.user.get('current')
        # Semanas já consultadas no Redmine nesta execução do app
        self.weeks_updated = set()

    def load_from_file(self):
        try:
            with open('tasks.pkl', 'rb') as arquivo:
                cache = pickle.load(arquivo)
                self.me = None if cache.get('user') is None else User(self.redmine.user, attributes=cache.get('user'))
                self.tasks_by_id = cache.get('tasks')
                self.week_cache = cache.get('weeks')
                self.working_task = cache.get('working_task')
                self.current_working_tasks = cache.get('current_working_tasks')
        except (FileNotFoundError, EOFError):
            pass
            
    def save_to_file(self):
        print("Salvando dados...")
        try:
            with open('tasks.pkl', 'wb') as arquivo:
                cache = {'user': dict(self.me),
                        'tasks': self.tasks_by_id,
                         'weeks': self.week_cache,
                         'working_task': self.working_task,
                         'current_working_tasks': self.current_working_tasks}
                pickle.dump(cache, arquivo)
            
        except (FileNotFoundError, EOFError):
            pass

    def get_assigned_task(self):
        """Retorna a tarefa associada a mim em andamento"""
        working_issues = self.redmine.issue.filter(assigned_to_id=self.me.id)
        for issue in working_issues:
            if issue.status.name.startswith('DEV • Exec'):
                return issue.id
        return None

    def get_task_by_id(self, task_id):
        if self.tasks_by_id.get(task_id):
            print("Retornando tarefa do cache")
            return self.tasks_by_id.get(task_id)
        print("Consultando tarefa...")
        self.refresh_tasks([task_id])
        if self.tasks_by_id.get(task_id):
            return self.tasks_by_id.get(task_id)
        task = {
                    "id" : task_id,
                    "desc": "tarefa não encontrada",
                    "status" : "desconhecido"
                }
        return task

    def refresh_tasks(self, task_ids):
        """Consulta as tarefas no Redmine em uma única chamada e atualiza o cache (descrição e status)."""
        if not task_ids:
            return
        # status_id='*' para trazer também tarefas fechadas (o padrão do Redmine é só abertas)
        issues = self.redmine.issue.filter(
            issue_id=",".join(str(task_id) for task_id in task_ids),
            status_id='*'
        )
        for red_task in issues:
            self.tasks_by_id[red_task.id] = {
                "id": red_task.id,
                "desc": str(red_task.subject)[:150],
                "status": str(red_task.status)
            }

    def get_user_name(self):
        """Retorna o nome do usuário logado no Redmine."""
        try:
            return f"{self.me.firstname} {self.me.lastname}".strip()
        except AttributeError:
            return str(getattr(self.me, 'login', ''))

    def get_month_hours(self, day):
        """Retorna o total de horas lançadas pelo usuário no mês da data informada."""
        first_day = day.replace(day=1)
        last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        time_entries = self.redmine.time_entry.filter(
            user_id=self.me.id,
            from_date=first_day,
            to_date=last_day
        )
        return sum(self.get_round_time(te.hours) for te in time_entries)

    def get_cached_week(self, start_date, end_date):
        """Retorna a semana do cache local, sem consultar o Redmine."""
        return self.week_cache.get(str(start_date)+'-'+str(end_date), {})

    def get_round_time(self, hours):
        h = round(hours * 60)
        return h / 60.0

    def get_working_week(self, start_date, end_date, force=False):

        #self.update_working_task()

        week_key = str(start_date)+'-'+str(end_date)
        week = self.week_cache.get(week_key)
        #Se é a semana atual deve atualizar independente pra manter coerente com possiveis ajustes direto no redmine
        is_current_week = (start_date <= date.today() <= end_date)
        #Semanas passadas: consulta o Redmine uma vez por execução do app; depois usa o cache (ou force=True)
        if week is not None and not is_current_week and not force and week_key in self.weeks_updated:
            print('Achou no cache')
            return week

        time_entries = self.redmine.time_entry.filter(
            user_id=self.me.id,
            from_date=start_date,
            to_date=end_date
        )

        #Separar as time entries por tarefa primeiro
        working_tasks_time_entries = {}
        for te in time_entries:
            te_per_issues = working_tasks_time_entries.setdefault(te.issue.id, [])
            te_per_issues.append(te)
                
        #Percorre todas tarefas/entradas pra separar por dias
        working_tasks_days_times = {}

        for task, it_time_entries in working_tasks_time_entries.items():
            working_task_days = {}
            for time_entry in it_time_entries:
                working_task_days.setdefault(str(time_entry.spent_on), 0)
                working_task_days[str(time_entry.spent_on)] += self.get_round_time(time_entry.hours)

            working_tasks_days_times[task] = working_task_days
        #Pega a tarefa que está atribuida para o usuário do redmine no momento
        assigned_task = self.get_assigned_task()
        # se tem tarefa atribuida e ela não tem horas registradas, adiciona dicionário vazio para que ela
        # apareça no board e o usuário possa registrar horas
        if assigned_task and not working_tasks_days_times.get(assigned_task):
            working_tasks_days_times[assigned_task] = {}
        
        #Atualiza descrição/status das tarefas da semana (o cache de tarefas guardava o status antigo)
        self.refresh_tasks(list(working_tasks_days_times.keys()))

        #salva no cache
        self.week_cache[week_key] = working_tasks_days_times
        self.weeks_updated.add(week_key)
        return working_tasks_days_times

    def register_time_entry(self, task_id, hours, description, activity_id):
        """Registra horas, descrição e atividade na tarefa informada."""
        if task_id is None:
            raise ValueError("Não há tarefa selecionada para registrar horas.")

        self.redmine.time_entry.create(
            issue_id=task_id,
            hours=hours,
            comments=description,
            activity_id=activity_id
        )
        self.save_to_file()

    def get_time_entry_activities(self):
        """Retorna as atividades disponíveis para registros de horas."""
        return list(self.redmine.enumeration.filter(resource="time_entry_activities"))