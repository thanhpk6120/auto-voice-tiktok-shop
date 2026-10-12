import subprocess
import sys

def main():
    print("Running tests...")
    try:
        # Check if pytest is available
        subprocess.check_call([sys.executable, "-m", "pytest", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Using pytest...")
        res = subprocess.call([sys.executable, "-m", "pytest", "tests/", "-q"])
    except subprocess.CalledProcessError:
        print("pytest not found, falling back to unittest...")
        res = subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    
    sys.exit(res)

if __name__ == "__main__":
    main()
