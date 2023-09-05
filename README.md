# pypaas

wget https://raw.githubusercontent.com/STOCKZE/pypaas/main/install_pypaas.sh

chmod +x install_pypaas.sh

sudo ./install_pypaas.sh


docker ps -a

docker stop $(docker ps -a -q)

docker rm $(docker ps -a -q)

docker system prune -a

docker ps -a
