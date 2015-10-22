#!/bin/bash

docker run -it -v $HOME/.ssh:/root/.ssh -v "$(PWD)/playbook.sh:/playbook.sh" -v "$(PWD)/ansible:/ansible" -v "$(PWD)/inventory:/inventory" trav/ansible-parted /bin/bash
