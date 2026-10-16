"""Panel-owned command documentation. Display and copy only; never execute."""
from command_reference import command_tokens


REFERENCES = {
    'Power': ('Raspberry Pi', 'Read only', (
        ('Check power warnings', 'vcgencmd get_throttled',
         'Read the Pi firmware flags when the panel is slow or reports a power warning.',
         '0x0 means no flags. Nonzero can include earlier warnings; it does not always mean a fault is active now.'),
    )),
    'Ubuntu checks': ('Ubuntu room computer', 'Check in this order', (
        ('Confirm the computer', 'hostname', 'Check which computer this Terminal is connected to.',
         'A host name. Confirm it is the room computer before continuing.'),
        ('Check running time and load', 'uptime', 'See time since boot and recent system load.',
         'Uptime and load averages. Load is not a CPU percentage.'),
        ('Check memory', 'free -m', 'Inspect memory in MiB when the room computer feels slow.',
         'Memory totals and available/free space. Cached memory is not automatically a problem.'),
        ('Check storage', 'df -h /', 'Check space on the root filesystem before collecting more data.',
         'Filesystem size, used space, available space and use percentage.'),
        ('Inspect existing sessions', 'tmux list-sessions', 'Look for existing sessions before considering a service start.',
         'Session names, or no server. A session name alone does not prove the service is healthy.'),
        ('Load the ROS environment', 'source /opt/ros/indigo/setup.bash',
         'Make the installed ROS tools available in this Terminal. This does not start ROS.',
         'Usually no output. If the file is missing, stop and check the installed setup with staff.'),
        ('Load the room workspace', 'source ~/catkin_ws/devel/setup.bash',
         'Add the installed room packages to this Terminal after loading ROS.',
         'Usually no output. Keep using the same Terminal for the next check.'),
        ('List advertised services', 'timeout 10 rosservice list',
         'Ask the configured ROS master for service names, with a ten-second time limit.',
         'Service names, an error or a timeout. Names show registration, not working sensors or devices.'),
    )),
    'Start services': ('Ubuntu room computer', 'Room host only · replaces sessions', (
        ('Start the ROS session', 'cd ~/catkin_ws/src/scr_control && python startROS.py',
         'Only after studies are stopped, ownership is checked and the existing sessions are understood.',
         'The launcher replaces the ROS session. Inspect its output and check services before using controls.'),
        ('Start the Status session', 'cd ~/scr.status_display && python startStatus.py',
         'Use only when the room host has decided the shared TV/Status session must be started.',
         'The launcher replaces Status. Check the TV and required feeds; a session name is not a health check.'),
    )),
    'Restart computer': ('Ubuntu room computer', 'Room host only · interrupts shared work', (
        ('Restart the room computer', 'sudo reboot',
         'Use after recordings have stopped and room users have coordinated the interruption.',
         'The connection ends. Wait for the desktop/network, then check ROS and Status; autostart is not assured.'),
    )),
}
DOCUMENTATION = {
    'Power': ('Raspberry Pi power flags', 'https://github.com/raspberrypi/documentation/blob/master/documentation/asciidoc/computers/os/graphics-utilities.adoc#get_throttled'),
    'Ubuntu checks': ('How the time limit works', 'https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html'),
    'Start services': ('Room operating guide', 'https://github.com/LESA-RPI/scr.touch_panel/blob/experiment/fresh-pi-setup-20261013/WORKFLOWS.md#before-connected-control'),
    'Restart computer': ('Room recovery guide', 'https://github.com/LESA-RPI/scr.touch_panel/blob/experiment/fresh-pi-setup-20261013/WORKFLOWS.md#switching-and-recovery'),
}


def reference(title):
    machine, effect, items = REFERENCES.get(title, ('', '', ()))
    docs = DOCUMENTATION.get(title)
    return {'machine':machine, 'effect':effect, 'documentation':{'label':docs[0], 'url':docs[1]} if docs else None,
            'steps':[{'title':label,'commands':code,'why':why,'expect':expect,
                      'command_tokens':command_tokens(code)} for label,code,why,expect in items]}


def commands(title):
    return '\n\n'.join(step['commands'] for step in reference(title)['steps'])
