# QVirtual-Machine.Kbit777

Projekt **Qwantum VM 2.9** — lokalny symulator obwodów kwantowych oparty na Pythonie, FastAPI i Qiskit Aer.

## Pakiet Windows

Pakiet Qwantum VM 2.9 został przygotowany jako archiwum ZIP w rozmowie, ale nie został jeszcze dołączony do tego repozytorium. Aby opublikować go tutaj, prześlij plik `Qwantum_VM_Windows_2.9.zip` do katalogu głównego repozytorium przez GitHub: **Add file → Upload files → Commit changes**.

## Uruchomienie w Windows 10/11

1. Rozpakuj archiwum ZIP.
2. Zainstaluj Python 3.12 64-bit.
3. Uruchom `install_windows.bat`.
4. Uruchom `run_windows.bat`.
5. Otwórz `http://127.0.0.1:8000`.

## Funkcje wersji 2.9

- Edytor obwodów z bramkami jedno- i dwukubitowymi.
- Wektor stanu oraz ewolucja stanu po kolejnych bramkach.
- Porównanie idealnego rozkładu i rozkładu z modelem szumu.
- Analiza stabilności pomiarów przy różnych wartościach `shots`, z metryką TVD.
- Historia i porównywanie eksperymentów, import/eksport JSON i eksport CSV.
- Diagnostyka API i testy.

## Ważne ograniczenia

Qwantum VM jest **symulatorem programowym**, a nie fizycznym procesorem kwantowym. Maksymalny rozmiar obwodu w tej wersji to 8 kubitów. Wizualizacja 777 węzłów nie oznacza 777 fizycznych kubitów. Model szumu jest uproszczony; wyniki nie są certyfikacją sprzętu kwantowego.

W środowisku przygotowania paczki składnia Pythona i JavaScript oraz integralność ZIP zostały sprawdzone, ale pełny zestaw testów Qiskit Aer nie został potwierdzony, ponieważ biblioteka nie była dostępna w tym środowisku.
