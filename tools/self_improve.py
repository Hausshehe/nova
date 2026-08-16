import os
import shutil
import datetime


BASE_DIR = "/data/data/com.termux/files/home/infoney"
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
WORKSPACE_DIR = os.path.join(BASE_DIR, "workspace")


def backup_file(path):
    if not os.path.exists(path):
        return False

    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    filename = os.path.basename(path)

    backup_path = os.path.join(
        BACKUP_DIR,
        f"{filename}.{timestamp}.bak"
    )

    shutil.copy2(path, backup_path)

    return True


def list_tools():
    tools = []

    if not os.path.exists(TOOLS_DIR):
        return tools

    for filename in os.listdir(TOOLS_DIR):

        if filename.endswith(".py") and not filename.startswith("_"):

            tools.append(filename[:-3])

    return tools


def get_workspace():
    os.makedirs(WORKSPACE_DIR, exist_ok=True)

    return WORKSPACE_DIR


def self_improvement_status():

    return {
        "tools_directory": TOOLS_DIR,
        "workspace_directory": WORKSPACE_DIR,
        "backup_directory": BACKUP_DIR,
        "available_tools": list_tools()
    }


if __name__ == "__main__":

    print("🧠 Nova self-improvement system")

    status = self_improvement_status()

    print("🧰 Tools:", status["available_tools"])

    print("📁 Workspace:", status["workspace_directory"])

    print("💾 Backups:", status["backup_directory"])
