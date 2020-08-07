import os
import re
import shutil
import subprocess
import sys

try:
    import xmltodict
except ImportError:
    raise Exception("Please, install xmltodict to proceed. (pip install xmltodict)")

RE_MACHINE_NAME = "- {1,}([a-zA-Z0-9_]+) {1,}shut (on|off)"
RE_SNAPSHOT_NAME = "([a-zA-Z0-9_]+) {1,}([0-9\-\:]+ ){2}.+shutoff"
ASCII_ART = """
         _nnnn_                      
        dGGGGMMb     ,--------------.
       @p~qp~~qMb    | Linux Rules! |
       M|@||@) M|   _;..............'
       @,----.JM| -'
      JS^\__/  qKL
     dZP        qKRb
    dZP          qKKb
   fZP            SMMb
   HZM            MMMM
   FqM            MMMM
 __| '.        |\dS'qML
 |    `.       | `' \Zq
_)      \.___.,|     .'
\____   )MMMMMM|   .'
     `-'       `--' hjm
"""


class KVMLibvirtBackup:
    def __init__(self):
        self.machines = []
        self.disk_list = []
        self.snapshot_names = []
        self.machine_name = None
        self.main_xml = None
        self.backup_path = None
        self.backup_folder = None
        self.__get_available_machines()
        print ASCII_ART

    def main(self):
        """
        This is the main method, that interacts with the user
        :return: None
        """
        # Checks if the user has machines to save
        if not self.machines:
            print "## Seems that you don\'t have any available machine. Exiting..."
            sys.exit(0)
        print "\n## Welcome to KVM/Libvirt Machine Backup. Please, make sure to turn off the VM that you want to use."
        print "## You can backup the following machines:\n"
        for item in self.machines:
            print '- {}'.format(item)

        # Asks for the machine name
        while True:
            self.machine_name = raw_input("\nPlease, inform the name of the machine you want to save: ")
            if self.machine_name not in self.machines:
                print "## That is not a valid machine\n"
                continue
            break

        # Asks for the path in which the files are going to be saved
        while True:
            self.backup_path = raw_input("Please, insert the path that you want to save the files: ")
            if not os.path.isdir(self.backup_path):
                print("Invalid path")
                continue
            break

        # Process removes previous backup files for that machine
        choice = raw_input("If exists, this process will remove previous backups for this VM. Continue? (Y/n)\n")
        if choice and choice != 'Y':
            print "## Exiting..."
            sys.exit(0)

        # Do the magic
        self.__backup()
        print "\n#### The Backup has finished ####\n"
        self.__how_to_restore()

    def __get_available_machines(self):
        """
        This method will retrieve all virtual machines available
        :return: self.machines
        """
        self.machines = [] if self.machines else self.machines
        for item in re.findall(RE_MACHINE_NAME, self.run_command("virsh list --all")):
            self.machines.append(item[0])
        return self.machines

    def __backup(self):
        """
        This method will walk through the all backup process
        :return:
        """
        # Create the backup folder
        self.backup_folder = os.path.join(self.backup_path, '{}_backup'.format(self.machine_name))
        if os.path.isdir(self.backup_folder):
            shutil.rmtree(self.backup_folder, ignore_errors=True)
        os.mkdir(self.backup_folder)

        # Shows the backup folder location
        print "## Saving the backup into: {}".format(self.backup_folder)

        # Main XML backup
        self.__main_xml_backup()

        # Backup the Disk file
        self.__disk_backup()

        # Snapshots XML backup
        self.__snapshot_xml_backup()

    def __main_xml_backup(self):
        """
        This method will save the main XML file for the Virtual Machine
        :return: None
        """
        # Gets the main XML file for the machine
        main_xml_path = os.path.join(self.backup_folder, '{}.xml'.format(self.machine_name))
        self.main_xml = self.run_command("virsh dumpxml {}".format(self.machine_name))
        with open(main_xml_path, 'w') as f:
            f.write(self.main_xml)
        print "## Main XML file saved"

    def __snapshot_xml_backup(self):
        """
        This method will save the XML files for each Snapshot within the Virtual Machine
        :return: None
        """
        virsh_output = self.run_command("sudo virsh snapshot-list {}".format(self.machine_name))
        for item in re.findall(RE_SNAPSHOT_NAME, virsh_output):
            self.snapshot_names.append(item[0])

        if not self.snapshot_names:
            print "## This machine does not have any snapshots."
            return None

        for item in self.snapshot_names:
            print "## Copying \'{}\' snapshot XML".format(item)
            dmp_path = os.path.join(self.backup_folder, item)
            cmd = "sudo virsh snapshot-dumpxml --security-info {} {} > {}.xml".format(self.machine_name, item, dmp_path)
            self.run_command(cmd)

    def __disk_backup(self):
        """
        This Method will copy the Virtual Machine disk file
        :return: None
        """
        main_xml = xmltodict.parse(self.main_xml)
        disks = main_xml['domain']['devices']['disk']
        if type(disks) == list:
            for item in disks:
                if 'source' in item:
                    self.disk_list.append(item['source']['@file'])
        else:
            self.disk_list.append(disks['source']['@file'])

        for item in self.disk_list:
            print "## Copying disk \'{}\'".format(item)
            shutil.copy(item, self.backup_folder)

    def __how_to_restore(self):
        """
        This method will print the required commands to restore the Virtual Machine
        :return: None
        """
        print "To import VM \'{}\' in the new machine, you should run the following " \
              "commands: \n".format(self.machine_name)

        # Restoring the Disks
        for item in self.disk_list:
            bkp_path = os.path.join(self.backup_folder, os.path.basename(item))
            print "sudo cp {} {}".format(bkp_path, os.path.dirname(item))

        # Restoring the main XML
        print "sudo virsh define " \
              "--file {}".format(os.path.join(self.backup_folder, '{}.xml'.format(self.machine_name)))

        # Restoring the Snapshots
        for item in self.snapshot_names:
            print "sudo virsh snapshot-create {} {} " \
                  "--redefine".format(self.machine_name, os.path.join(self.backup_folder, '{}.xml'.format(item)))

        print("\n\n")

    @staticmethod
    def run_command(cmd):
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True)
        (output, err) = p.communicate()
        p.wait()
        return output


if __name__ == '__main__':
    bkp = KVMLibvirtBackup()
    bkp.main()
