# VHS: демо A «цитата не в тех устах» (<10с). Рендер: vhs scripts/demo/misattribution.en.tape
# Вердикт снятия маркера считает живой валидатор атрибуции (misattribution_demo.py), не хардкод.
Output assets/demo-misattribution-en.gif
Require python3
Set Shell "bash"
Set FontSize 22
Set Width 1120
Set Height 620
Set Padding 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms
Hide
Type "export OLLAMA_HOST=http://127.0.0.1:59999" Enter
Type "consilium() { python3 scripts/demo/misattribution_demo.py --no-prompt --en; }" Enter
Type "clear" Enter
Show
Sleep 600ms
Type "consilium render-session"
Sleep 500ms
Enter
Sleep 9s
