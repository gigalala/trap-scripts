from os import system

GITHUB_URL = 'https://github.com/gigalala/trap-scripts.git'


def change_battery():
    return -1


def stay_on():
    return True


def update(version='latest'):
    branch = None
    if version:
        branch = version
    system(f'git clone --branch ${branch} GITHUB_URL')
    system('mv trap-scripts/* /')
