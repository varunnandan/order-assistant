import sys
from dulwich import porcelain
from dulwich.repo import Repo

def main():
    target_url = "https://github.com/varunnandan/order-assistant.git"
    repo = Repo(".")
    print(f"Adding remote origin: {target_url}")
    
    # Check if origin already exists
    config = repo.get_config()
    try:
        porcelain.remote_add(repo, "origin", target_url)
    except Exception as e:
        print(f"Remote add info: {e}")

    print("Attempting to push to remote repository...")
    try:
        porcelain.push(repo, target_url, b"refs/heads/main")
        print("Successfully pushed code to GitHub repository!")
    except Exception as push_err:
        print(f"Push result: {push_err}")

if __name__ == "__main__":
    main()
