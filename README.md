# ASR-Plus

install :

cd ~/domoticz/plugins 

mkdir ASRPlus

sudo apt-get update

sudo apt-get install git

git clone https://github.com/Erwanweb/ASR-Plus.git ASRPlus

cd ASRPlus

sudo chmod +x plugin.py

sudo /etc/init.d/domoticz.sh restart

Upgrade :

cd ~/domoticz/plugins/ASRPlus

git reset --hard

git pull --force

sudo chmod +x plugin.py

sudo /etc/init.d/domoticz.sh restart
