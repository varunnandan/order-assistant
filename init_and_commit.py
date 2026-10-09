import os
from dulwich import porcelain
from dulwich.repo import Repo

def main():
    if not os.path.exists(".git"):
        repo = porcelain.init(".")
        print("Initialized Git repository at .git")
    else:
        repo = Repo(".")
        print("Opened existing Git repository at .git")

    porcelain.add(repo, ".")
    print("Staged files in repository")

    commit_id = porcelain.commit(
        repo,
        message=b"feat: complete order assistant web app with tools, agent loop, UI and tests",
        author=b"Order Assistant AI <assistant@order-app.local>",
        committer=b"Order Assistant AI <assistant@order-app.local>"
    )
    print(f"Committed successfully with SHA: {commit_id.decode('utf-8')}")

if __name__ == "__main__":
    main()
