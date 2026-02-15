1) Clone the repo
git clone <repo-url>
cd diad_poc

2) Make sure python3 works
python3 --version
python3 -m tkinter   (a small window should open)

3) Create the virtual environment (use python3, NOT python)
python3 -m venv .venv
source .venv/bin/activate

4) Install dependencies
pip install duckdb pandas

5) Verify everything works
python -c "import tkinter, duckdb, pandas; print('all good')"

6) Pull the model (one time)
ollama pull duckdb-nsql

7) Run the app
python run_ui.py
