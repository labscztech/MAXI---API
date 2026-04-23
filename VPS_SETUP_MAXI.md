# Instalação Limpa e Desfazimento na VPS da Hostinger

Sua VPS já usa o Traefik para controle das rotas web (`0.0.0.0:80`).
Não precisaremos mais de `certbot`, `nginx` ou `pm2` raiz em seu servidor.

O código de roteamento já está incluído nativamente via `docker-compose.yml`.

## 1. Conectar na sua VPS
```bash
ssh root@46.202.147.155
```

## 2. Limpar o rastro do Nginx falho
Como o nginx local estava causando impacto tentando subir em cima da mesma porta do seu Traefik nativo, rode estes comandos para removê-lo completamente com segurança e restaurar o terminal como era antes:
```bash
apt-get purge nginx nginx-common -y
apt-get autoremove -y
```

## 3. Tudo Pronto!
A sua nuvem já possui `docker` e `docker-compose` criados no molde da Hostinger. 

Conforme as variáveis SSH estão cadastradas no seu GitHub, agora basta você fazer o **`push` do seu repositório MAXI no Visual Studio Code**.

O _GitHub Actions_ irá automaticamente se conectar ao servidor e iniciar tudo sozinho:
1. Copiar todos os arquivos para a VPS;
2. Montar a Imagem Docker (`maxi-dashboard`) isolando o Python;
3. Integrá-lo à rede do Traefik indicando-o a escutar o `/fusion` do domínio `zanontech.com`.
