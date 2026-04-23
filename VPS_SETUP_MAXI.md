# Instalação e Configuração na VPS Hostinger para o Projeto MAXI

Este arquivo documenta os passos necessários que você precisará rodar **uma única vez** no seu servidor VPS para configurar o domínio, SSL, e o gerenciador de tarefas do Python em background. 

Todas as atualizações de código e restart posteriores serão feitos automaticamente pelo GitHub Actions.

## 1. Conectar na sua VPS
Acesse o terminal / Prompt de Comando e conecte por SSH:
```bash
ssh root@46.202.147.155
```

## 2. Instalar Dependências de Sistema

Vamos instalar o Nginx (servidor web), Node/PM2 (orquestrador) e Python3/venv (para rodar a API):

```bash
apt update && apt upgrade -y
apt install -y nginx rsync curl python3 python3-venv python3-pip certbot python3-certbot-nginx

# Instalar NPM + PM2 globalmente
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
apt install -y nodejs
npm install -g pm2
```

## 3. Preparar a Pasta do Projeto
Vamos garantir que a pasta do projeto de destino existe:
```bash
mkdir -p /root/projetos/MAXI
```
> Após rodar os comandos de Setup e Nginx, **lembre-se de configurar e executar seu Git Push para o Github**, pois apenas depois disso a pasta acima estará com os arquivos preenchidos.

## 4. Configurar o Nginx (Proxy para o FastAPI)

O arquivo do Nginx servirá os pedidos na porta HTTP padrão e redirecionará para a FastAPI porta 8000 na retaguarda.

Remova a página default padrão:
```bash
rm /etc/nginx/sites-enabled/default
```

Abra o arquivo para configurar o Domínio do MAXI:
```bash
nano /etc/nginx/conf.d/maxi.conf
```
*Cole o seguinte conteúdo dentro do nano:*
```nginx
server {
    listen 80;
    server_name zanontech.com www.zanontech.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Suporte a WebSockets
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```
*No editor Nano, salve apertando `CTRL+O` depois `ENTER`, e saia com `CTRL+X`.*

Para validar se o comando ficou escrito corretamente e reiniciar o servidor Nginx:
```bash
nginx -t
systemctl restart nginx
```

## 5. Gerar SSL para o Domínio

Para proteger sua conexão via `https://` o Let's Encrypt fornecerá um certificado gratuito. (O domínio `zanontech.com` precisa estar com os apontamentos DNS apontando para o IP 46.202.147.155 no Registro do domínio ou na Cloudflare).

Execute o certbot:
```bash
certbot --nginx -d zanontech.com -d www.zanontech.com
```

## Finalizando
Tudo do lado do Servidor está pronto. Para habilitar o seu projeto online basta seguir com o Git Push do repositório no seu computador local, como faria normalmente. Se já configurou as variáveis Secrets no GitHub:
1. Faça o commit e push da sua máquina pra branch `main`.
2. Acompanhe a Action aba *Actions*.
3. O PM2 ligará o Uvicorn do seu dashboard rodando na porta 8000.
4. Você poderá acessar o site pelo `https://zanontech.com` e a API no modo seguro.
