#!/usr/bin/python

DOCUMENTATION = '''
---
module: partitions
author: "Travis Dixon (@thetrav)"
version_added: "0.1"
short_description: Manage partitions via parted
requirements: [ parted ]
description:
    - Manage partitions via parted.
options:
    device:
        required: true
        description:
            - Device to select (eg: /dev/sdb)
    label:
        required: false
        default: "gpt"
        choices: [ bsd, loop, gpt, mac, msdos, pc98, sun ]
        description:
            - argument for mklabel
    unit:
        required: false
        default: compact
        choices: [s, B, kB, MB, GB, TB, compact, cyl, chs, %, kiB, MiB, GiB, TiB]
        description:
        - unit of input/output
    part_type:
        required: false
        default: primary
        choices: [ primary, extended ]
        description:
            - type of partition
    fs_type:
        required: false
        default: ext4
        choices: [ ext2, ext3, ext4, fat16, fat32, hfs, hfs+, hfsx, linux-swap, NTFS, reiserfs, ufs, btrfs ]
        description:
            - type of file system
    start:
        required: true
        description:
            - start of partition
    end:
        required: true
        description:
            - end of partition
'''

EXAMPLES = '''
# create a single primary ext4 partition using all of the disk
- partition: device=/dev/sdb start=0 end=-1
# create a 1tb primary ext4 paritition and a second partiion using the remaining space
- partition: device=/dev/sdb unit=GB start="{{item.start}}" end="{{item.end}}"
  with_items:
  - {start: 0, end: 1100 }
  - {start: 1100, end: -1 }
'''

def read_fixed_width_table(table):
    titles = table[0].split()

    column_starts = [table[0].index(title) for title in titles]
    column_ends = [num - 1 for num in column_starts[1:]] + [len(table[0])]
    columns = zip(column_starts, column_ends)

    values = [[line[column[0]:column[1]].strip() for column in columns] for line in table[1:]]
    return [dict(zip([title.strip() for title in titles], line)) for line in values]

class Partition(object):
    def __init__(self, table, max_size):
        def numify(str):
            return(''.join(c for c in str if c in '-+.1234567890'))
        self.max_size = numify(max_size)
        self.number = table['Number']
        self.start = numify(table['Start'])
        self.end = numify(table['End'])
        if(self.end < 0):
            self.end = self.max_size

    def same(self, start, end):
        a_end = int(end)
        if(a_end < 0): 
            a_end = self.max_size
        def equal(a, b):
            return round(float(a), 2) == round(float(b), 2)
        res = equal(self.start, start) and equal(self.end, a_end)
        # print "comparing {} {} with {} {} got {}".format(start, a_end, self.start, self.end, res)
        return res

    def overlaps(self, start, end):
        #horrible conversions into a type I can compare
        def floatify(a):
            return round(float(a), 2)
        start_a = floatify(start)
        start_b = floatify(self.start)
        end_a = end
        if(end_a < 0): 
            end_a = self.max_size
        end_a = floatify(end_a)
        end_b = floatify(self.end)

        #case of adjacent blocks
        if start_a == end_b or end_a == start_b:
            return False
        #case of overlapping blocks
        return end_a >= start_b and start_a <= end_b

class PartitionTable(object):
    def __init__(self, device, unit):
        self.device = device
        self.unit = unit

    def refresh(self, run_command):
        cmd = "parted {device} unit {unit} print".format(device=self.device, unit = self.unit)
        rc, stdout, stderr = run_command(cmd, use_unsafe_shell=False, data=None)
        if rc != 0:
            return ""
        lines = stdout.split("\n")
        def read_field(predicate, default=""):
            found = [line.split(': ')[1] for line in lines if predicate(line)][:1]
            return found[0] if found else default

        self.label = read_field(lambda line: "Partition Table:" in line)
        self.size = read_field(lambda line: "Disk {}:".format(self.device) in line)
        
        table = []
        for line in lines:
            if len(table) == 0:
                if line.startswith("Number"):
                    table = [line]
            else:
                if len(line.strip()) > 0:
                    table = table + [line] 

        self.table = [Partition(partition, self.size) for partition in read_fixed_width_table(table)]


    def set_label(self, run_command, label):
        self.refresh(run_command)

        if self.label == label:
            return False
        else:
            cmd = "parted -s -a optimal {device} -- mklabel {label}".format(device = self.device, label=label)
            rc, stdout, stderr = run_command(cmd)
            if rc != 0:
                return False
            self.refresh(run_command)
            return True
        

    def set_partition(self, run_command, unit, part_type, fs_type, start, end):
        self.refresh(run_command)

        if len(filter(lambda partition: partition.same(start, end), self.table)) > 0:
            return False

        #remove overlapping
        for partition in self.table:
            if partition.overlaps(start, end):
                cmd = "parted -s -a optimal {device} -- unit {unit} rm {number}".format(
                    device = self.device, 
                    unit = self.unit, 
                    number = partition.number)
                rc, stdout, stderr = run_command(cmd)
                if rc != 0:
                    raise ValueError("{} {} {} {}".format(rc, stdout, stderr, cmd))
        
        #create new
        cmd = "parted -s -a optimal {device} -- unit {unit} mkpart {part_type} {fs_type} {start} {end}".format(
            device = self.device,
            unit = self.unit,
            part_type = part_type,
            fs_type = fs_type,
            start = start,
            end = end)
        rc, stdout, stderr = run_command(cmd)
        if rc != 0:
            raise ValueError("{} {} {} {}".format(rc, stdout, stderr, cmd))
        self.refresh(run_command)
        return True

def main():
    module = AnsibleModule(
        argument_spec = dict(
            device=dict(required=True, type='str'),
            label=dict(default='gpt', choices=['bsd', 'loop', 'gpt', 'mac', 'msdos', 'pc98', 'sun'], type='str'),
            unit=dict(default='compact', choices=['s', 'B', 'kB', 'MB', 'GB', 'TB', 'compact', 'cyl', 'chs', '%', 'kiB', 'MiB', 'GiB', 'TiB'], type='str'),
            part_type=dict(default='primary', choices=['primary', 'extended'], type='str'),
            fs_type=dict(default='ext4', choices=['ext2', 'ext3', 'ext4', 'fat16', 'fat32', 'hfs', 'hfs+', 'hfsx', 'linux-swap', 'NTFS', 'reiserfs', 'ufs', 'btrfs'], type='str'),
            start=dict(required=True, type='int'),
            end=dict(required=True, type='int'),
        ),
        supports_check_mode=True)
    def param(key):
        return module.params[key]

    def params(*args):
        return [param(arg) for arg in args]
    result = {}

    partition_table = PartitionTable(*params('device', 'unit'))
    changed_label = partition_table.set_label(module.run_command, param("label"))

    changed_table = partition_table.set_partition(module.run_command, *params('unit', 'part_type', 'fs_type', 'start', 'end'))
    
    result['changed'] = changed_label or changed_table
    result['partition_table'] = [p.__dict__ for p in partition_table.table]
    module.exit_json(**result)


# import module snippets
from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
