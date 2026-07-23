# VHS: демо «клэш совета» ИЛЛЮСТРАТИВНЫЙ (<11с). vhs scripts/demo/clash.tape
# 🟡 доводы генерит хост (не верифицируется); 🔵-строку сверяет живой гейт (clash_demo.py).
Output assets/demo-clash.gif
Require python3
Set Shell "bash"
Set FontSize 21
Set Width 1180
Set Height 640
Set Padding 30
Set Theme "Catppuccin Mocha"
Set TypingSpeed 30ms
Hide
Type "export OLLAMA_HOST=http://127.0.0.1:59999" Enter
Type "consilium() { python3 scripts/demo/clash_demo.py --no-prompt; }" Enter
Type "clear" Enter
Show
Sleep 600ms
Type "consilium «тяну четыре направления. на чём сфокусироваться?»"
Sleep 500ms
Enter
Sleep 10s
