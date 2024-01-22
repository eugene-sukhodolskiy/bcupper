import os
import tarfile
import json
from ftplib import FTP
import pysftp
from datetime import datetime

def get_folder_size(path):
	total_size = 0
	with os.scandir(path) as it:
		for entry in it:
			if entry.is_file():
				total_size += entry.stat().st_size
			elif entry.is_dir():
				total_size += get_folder_size(entry.path)
	return total_size

def get_free_space(path):
	statvfs = os.statvfs(path)
	return statvfs.f_frsize * statvfs.f_bavail

def ensure_directory_exists(directory_path):
	if not os.path.exists(directory_path):
		os.makedirs(directory_path)

def check_and_delete_oldest_backup(destination, max_backups):
	backups = sorted(os.listdir(destination))
	if len(backups) > max_backups:
		return delete_oldest_backup(destination)

def delete_oldest_backup(destination):
	backups = sorted(os.listdir(destination))
	oldest_backup = os.path.join(destination, backups[0])
	os.remove(oldest_backup)
	print(f"Removed oldest backup <{oldest_backup}>");
	return oldest_backup

def create_local_backup(source, destination, max_backups, free_space):
	if free_space < get_folder_size(source):
		print("Not enough memory")
		delete_oldest_backup(destination)

	current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
	backup_name = f"{current_time}-{os.path.basename(source)}"
	with tarfile.open(os.path.join(destination, backup_name), 'w:gz') as tar:
		tar.add(source, arcname=os.path.basename(source))

	check_and_delete_oldest_backup(destination, max_backups)
	return backup_name

def get_ftp_connection(protocol, host, user, password):
	if protocol == "sftp":
		cnopts = pysftp.CnOpts()
		cnopts.hostkeys = None
		return pysftp.Connection(host, username=user, password=password, cnopts=cnopts)
	else:
		return FTP(host, user, password)

def create_ftp_backup(source, destination, max_backups, ftp_protocol, ftp_host, ftp_user, ftp_password):
	with get_ftp_connection(ftp_protocol, ftp_host, ftp_user, ftp_password) as ftp:
		ftp.cwd(destination)

		current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
		backup_name = f"{current_time}-{os.path.basename(source)}"
		backup_path = os.path.join("/tmp", backup_name)
		with tarfile.open(backup_path, 'w:gz') as tar:
			tar.add(source, arcname=os.path.basename(source))

		if ftp_protocol == "sftp":
			ftp.put(backup_path, preserve_mtime=True)
		else:
			with open(backup_path, 'rb') as file:
				ftp.storbinary(f"STOR {backup_name}", file)

		os.remove(backup_path)

		if ftp_protocol == "sftp":
			ftp_backups = ftp.listdir()
		else:
			ftp_backups = ftp.nlst()

		if len(ftp_backups) > max_backups:
			if ftp_protocol == "sftp":
				oldest_backup = min(ftp_backups, key=lambda x: ftp.stat(x).st_mtime)
				ftp.remove(oldest_backup)
			else:
				oldest_backup = min(ftp_backups, key=lambda x: ftp.voidcmd(f"MDTM {x}"))
				ftp.delete(oldest_backup)
			print(f"Removed oldest backup <{oldest_backup}>");

def main():
	with open('config.json') as f:
		config = json.load(f)

	for directory in config['directories']:
		source_directory = directory['source']
		destination_directory = directory['destination']

		print(f"Backup <{source_directory}>")

		if not os.path.exists(source_directory):
			print(f"[WARNING] <{source_directory}> was not found")
			continue

		ensure_directory_exists(destination_directory)
		max_backups = directory.get('max_backups', float('inf'))
		
		if 'ftp' in directory:
			ftp_config = directory['ftp']
			print(f"to FTP server <{ftp_config['host']}>");
			name_of_backup = create_ftp_backup(source_directory, destination_directory, max_backups, ftp_config["protocol"], ftp_config['host'], ftp_config['user'], ftp_config['password'])
		else:
			free_space = get_free_space(destination_directory)
			name_of_backup = create_local_backup(source_directory, destination_directory, max_backups, free_space)

		print(f"[SUCCESS] backup <{source_directory}> to <{destination_directory}> with name `{name_of_backup}` was created")

if __name__ == "__main__":
	main()
