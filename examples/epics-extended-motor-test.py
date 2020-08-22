#-------------------------------
import argparse

DEBUGGING = True


# DONOT import Agent from reactive_agent!!!!

parser = argparse.ArgumentParser(description='Set positions of DynAp motors on the trajectory.')

parser.add_argument('--default_eprefix', type=str, default='WORKSHOP01', help='default epics prefix')

parser.add_argument('--debug', action='store_true', help='Debug mode', default=DEBUGGING)

parser.add_argument('-v', '--verbose', action='count', default=0)

parser.add_argument('--conti', action='store_true', default=False, \
    help='continue forcing positions - otherwuise: quits after positions are set')

parser.add_argument('--cycles', type=int, default=15, help='maximum process cycles')

parser.add_argument('--cycle_period', type=float, default=0.2, help='process cycle period [seconds]')

_VERBOSE_ = 2

#global args
args = parser.parse_args()
#--------------------------------
# import sys
# sys.path.append(".")
# print(sys.path)

# epic-extended motor test code
from wrasc.epics_device_ra import EpicsExtendedMotor
from wrasc import reactive_agent as ra

list_of_motors = set()

# The default prefix is only used as a size reference to split the PV names to eprefix and device prefix.
default_eprefix = 'WORKS'

# read text file listing of all epics devices here
epics_devices_file = 'examples/data/lastsnapshot.snapshot'

for line in open(epics_devices_file):
    li=line.strip()
    if not li.startswith("#") and len(li) > 1:
        # TODO is this a motor record ?
        if '=' in line.rstrip():
            _full_name, _value = line.rstrip().split('=')
        else:
            _full_name = line.rstrip()
            _value = None
        
        _eprefix = _full_name[0:len(default_eprefix)]
        _dev_prefix, _motor_name_field = _full_name[len(default_eprefix):].split(':', maxsplit=1)
        
        if '.' in _motor_name_field:
            _spl = _motor_name_field.split('.', maxsplit=1)
            _motor_name = _spl[0]
            _field_name = '.' +  _spl[1]
        elif ':' in _motor_name_field:
            _spl = _motor_name_field.split(':', maxsplit=1)
            _motor_name = _spl[0]
            _field_name = ':' +  _spl[1]
        else:
            _motor_name = _motor_name_field
            _field_name = None
        
        # in this context, motor record is an epics device so:
        _dev_mot = _dev_prefix + ':' + _motor_name
        # install if this is a new motor
        _ra_dev_name = _dev_mot.replace(':','_').lower()
        if _ra_dev_name not in list_of_motors:
            list_of_motors.add(_ra_dev_name)
            
            exec_str = f"{_ra_dev_name} = EpicsExtendedMotor(dev_prefix='{_dev_mot}', eprefix='{_eprefix}')"
            exec(exec_str)
        # now the motor is installed, if there is a value, then insert that value into the motor agent!
        # preferraby using a device method

        if _value is not None: 
            exec_str = f"{_ra_dev_name}.set_saved_value(pvname='{_field_name}', value_str='{_value}')"
            exec(exec_str)
        

print(list_of_motors)


#=====================================================================================


# hop01_mot1 = EpicsExtendedMotor(dev_prefix='HOP01:MOT1', eprefix=default_eprefix)
# hop01_mot3 = EpicsExtendedMotor(dev_prefix='HOP01:MOT3', eprefix=default_eprefix)

hop01_mot1.activator_ag.poll_pr = lambda ag_self: True
hop01_mot3.activator_ag.poll_pr = lambda ag_self: hop01_mot1.deactivator_ag.poll.Var
hop01_mot4.activator_ag.poll_pr = lambda ag_self: hop01_mot3.deactivator_ag.poll.Var


#=====================================================================================


#=====================================================================================
# input('press a key or break...')
# dm module called to compile and install agents
agents_sorted_by_layer = ra.compile_n_install({}, globals().copy(), _eprefix)
# input('press any key to start the process loop...')
# dm module takes control of the process loop
ra.process_loop(agents_sorted_by_layer, args.cycles, cycle_period=args.cycle_period, debug=args.debug)

