from redminelib import Redmine
from redminelib.resources import User
from datetime import date
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
        self.updated_today = False

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
        red_task = None
        for red_task in self.redmine.issue.filter(issue_id=task_id):
            pass
        if red_task is not None:
            task = {
                    "id" : red_task.id,
                    "desc": str(red_task.subject)[:150],
                    "status" : str(red_task.status)
                }
            self.tasks_by_id[task_id] = task
            return task
        task = {
                    "id" : task_id,
                    "desc": "tarefa não encontrada",
                    "status" : "desconhecido"
                }
        return task
        
    def get_round_time(self, hours):
        h = round(hours * 60)
        return h / 60.0

    def get_working_week(self, start_date, end_date):
        
        #self.update_working_task()

        week = self.week_cache.get(str(start_date)+'-'+str(end_date))
        #Se é a semana atual deve atualizar independente pra manter coerente com possiveis ajustes direto no redmine
        is_current_week = (start_date <= date.today() <= end_date)
        #Atualiza somente quando abre o app (self.updated_today)
        if week is not None and not is_current_week and not self.updated_today:
            print('Achou no cache')
            self.updated_today = True
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
        
        #salva no cache
        self.week_cache[str(start_date)+'-'+str(end_date)] = working_tasks_days_times
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