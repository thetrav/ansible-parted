#!/bin/sh

ansible-playbook -vvvv --inventory-file=inventory ansible/main.yml
