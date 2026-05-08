RED SEB Portable

1. Mantenha o arquivo SEB.portable na mesma pasta do executavel.
2. Execute "Launch REDSEB Portable.bat".
3. Se quiser usar outro .seb: arraste o arquivo para o .bat ou rode:
   "Launch REDSEB Portable.bat" "C:\caminho\arquivo.seb"

Este modo portable:
- grava cache/logs/configuracao em .\PortableData
- ignora o servico instalado do SEB
- relaxa o kiosk/service apenas para execucao em usuario comum
- preserva User-Agent, headers SEB e o monitoramento remoto do fork
