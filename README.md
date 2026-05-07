Welcome to DIAD!

Diad is a tool that can be used to view and ask questions about data using natural langugae via local Ollama hosted models llama3.2 and duckdb-sql models

It is important to note that our application is only supported on MacOS devices that have an Apple Silicon chip and at least 16gn of ram is recommended for a fast experience

the easiest way to install our application is to go to realeases on the side and download the .pkg installer from there, it automatically installs and pulls dependencies such as python 3.12, Ollama, the models, creates a virtual environment for requirements install, and installs a core tkinter dependency. 

**IMPORTANT** before you install, you need to make sure you have manually downloaded the following dependencies, the installer does not download these

xcode developer tools: this can be installed with xcode-select --install
Homebrew: this can be installed with /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

it is also important to note that when clicking the .pkg file, it is very likely you will get an error that says macOS cannot verify this is a safe application, to continue with install make sure you do not click move to trash, go to System preferences -> privacy and security -> and scroll to security where you will see .pkg name and select "open anyways", this will begin the install.

For more information about our product and how it is best used, load it up, load a .csv, .xlsx, or .json file, name the project, select create, and hit the tips button on the left side of the screen.