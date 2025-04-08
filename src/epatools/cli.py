

BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
WHITE = "\033[37m"

RESET_ALL = "\033[0m"


def get_version(app, version):
    return f"{GREEN}{app}{RESET_ALL} (v{version})"

def print_app_title(title):
    print(title)
    print_line()

def print_line():
    print(f"{YELLOW}{'─'*50}{RESET_ALL}")

def print_command_title(title):
    print(f"{GREEN}{title}{RESET_ALL}")
    print("")

def print_command_title_with_app_info(app, version, title):
    version_text = get_version(app=app, version=version)
    print(f"{version_text} - {BLUE}{title}{RESET_ALL}")

def print_command(text):
    print(f"{BLUE}{text}{RESET_ALL}")


def print_error(text):
    print(f"{RED}{text}{RESET_ALL}")

