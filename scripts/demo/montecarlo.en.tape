# VHS: демо B «посчитано, не на глаз» (<10с). Рендер: vhs scripts/demo/montecarlo.en.tape
# Числа считает живой run_calculation (montecarlo_demo.py), сид 2026 — воспроизводимо.
Output assets/demo-montecarlo-en.gif
Require python3
Set Shell "bash"
Set FontSize 22
Set Width 1120
Set Height 620
Set Padding 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Hide
Type "export OLLAMA_HOST=http://127.0.0.1:59999" Enter
Type "consilium() { python3 scripts/demo/montecarlo_demo.py --no-prompt --en; }" Enter
Type "clear" Enter
Show
Sleep 600ms
Type "consilium calc"
Sleep 500ms
Enter
Sleep 9s
