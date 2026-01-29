# D.I.A.D. – Do It All Data (PoC)

A local, schema-aware data tool that lets you ask **plain-English questions** about CSV datasets and get **safe DuckDB SQL results** using a local LLM.

---

## Current Capabilities

- Load multiple CSV files into a local **DuckDB** database
- Automatically detect:
  - Tables and column names
  - **Categorical columns** and their unique values
- Display a clear **data catalog** in the terminal
- Accept **plain-English queries**
- Use a **local LLM (via Ollama)** to generate SQL
- Enforce safety:
  - SELECT-only queries
  - No destructive SQL
  - Automatic table joins when queries reference multiple datasets
- Preview results and export to `output.csv`

---

## Requirements

- **Python 3.10+**
- **Ollama** (local LLM runner)

Install Ollama: https://ollama.com

Pull a recommended model:
ollama pull duckdb-nsql

---

SETUP

1. Clone the repository
git clone <repo-url>
cd diad_poc

2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate   (macOS/Linux)

Windows:
.venv\Scripts\activate

3. Install dependencies
use pip to install 
duckdb and pandas 

4. Add CSV files
Place all CSV files into the data/ directory.
Each CSV is automatically loaded as a table.

---

RUN

python -m app.main data
or
python -m app.main data duckdb-nsql

---

USAGE

1. The app prints:
- Tables and columns
- Categorical columns with allowed values

2. Enter a plain-English query

3. The app generates SQL, runs it, previews results, and exports output.csv

Type "exit" to quit.
