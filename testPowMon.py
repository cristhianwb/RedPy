from WindowsPowerMonitor import WindowsPowerMonitor



def suspender():
    print("Suspend")

def wake():
    print("wake up")

if __name__ == "__main__":
        
    monitor = WindowsPowerMonitor(
        None, 
        on_suspend=suspender, 
        on_resume=wake
    )
    
    monitor.test()
    