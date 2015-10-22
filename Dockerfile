# https://github.com/ansible/ansible-docker-base
FROM ansible/ubuntu14.04-ansible:stable

RUN apt-get update -y

RUN apt-get dist-upgrade -y

RUN apt-get install -y curl

ADD ansible /ansible

CMD ansible-playbook --inventory-file /inventory /ansible/main.yml
