## Red Root Shell

Pacote da identidade de shell do root herdada da VM antiga da RED.

Inclui:
- `root.bashrc`
- `root.bash_profile`
- `root.profile`
- `00-red-header`
- `redpainel`

Uso no host alvo:

```bash
sudo /opt/redvm-repo/infraestrutura/scripts/apply_red_root_shell_identity.sh
```

Para trocar o hostname aplicado pelo script:

```bash
sudo TARGET_HOSTNAME=red /opt/redvm-repo/infraestrutura/scripts/apply_red_root_shell_identity.sh
```

O script:
- instala o shell customizado do root
- publica o `redpainel`
- ativa o MOTD da RED
- desativa os extras de cloud-init que poluem o login
- ajusta `hostname` e `/etc/hosts`
