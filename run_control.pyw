"""파이프라인 관제 프로그램 실행기 (더블클릭 또는 venv\\Scripts\\pythonw.exe run_control.pyw)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from control_app.ui import main

main()
