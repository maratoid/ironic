# Copyright (c) 2012 NTT DOCOMO, INC.
# Copyright 2010 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Mapping of bare metal node states.

Setting the node `power_state` is handled by the conductor's power
synchronization thread. Based on the power state retrieved from the driver
for the node, the state is set to POWER_ON or POWER_OFF, accordingly.
Should this fail, the `power_state` value is left unchanged, and the node
is placed into maintenance mode.

The `power_state` can also be set manually via the API. A failure to change
the state leaves the current state unchanged. The node is NOT placed into
maintenance mode in this case.
"""

from ironic.common import fsm


#####################
# Provisioning states
#####################

NOSTATE = None
""" No state information.

Default for the power and provision state of newly created nodes.
"""

ACTIVE = 'active'
""" Node is successfully deployed and associated with an instance. """

DEPLOYWAIT = 'wait call-back'
""" Node is waiting to be deployed.

This will be the node `provision_state` while the node is waiting for
the driver to finish deployment.
"""

DEPLOYING = 'deploying'
""" Node is ready to receive a deploy request, or is currently being deployed.

A node will have its `provision_state` set to DEPLOYING briefly before it
receives its initial deploy request. It will also move to this state from
DEPLOYWAIT after the callback is triggered and deployment is continued
(disk partitioning and image copying).
"""

DEPLOYFAIL = 'deploy failed'
""" Node deployment failed. """

DEPLOYDONE = 'deploy complete'
""" Node was successfully deployed.

This is mainly a target provision state used during deployment. A successfully
deployed node should go to ACTIVE status.
"""

DELETING = 'deleting'
""" Node is actively being torn down. """

DELETED = 'deleted'
""" Node tear down was successful.

This is mainly a target provision state used during node tear down. A
successful tear down leaves the node with a `provision_state` of NOSTATE.
"""

ERROR = 'error'
""" An error occurred during node processing.

The `last_error` attribute of the node details should contain an error message.
"""

REBUILD = 'rebuild'
""" Node is currently being rebuilt. """


##############
# Power states
##############

POWER_ON = 'power on'
""" Node is powered on. """

POWER_OFF = 'power off'
""" Node is powered off. """

REBOOT = 'rebooting'
""" Node is rebooting. """


#####################
# State machine model
#####################

machine = fsm.FSM()

# Add stable states
machine.add_state(NOSTATE)
machine.add_state(ACTIVE)
machine.add_state(ERROR)

# Add deploy* states
machine.add_state(DEPLOYDONE, target=ACTIVE)
machine.add_state(DEPLOYING, target=DEPLOYDONE)
machine.add_state(DEPLOYWAIT)
machine.add_state(DEPLOYFAIL)

# Add rebuild state
machine.add_state(REBUILD, target=DEPLOYDONE)

# Add delete* states
machine.add_state(DELETED, target=NOSTATE)
machine.add_state(DELETING, target=DELETED)


# From NOSTATE, a deployment may be started
machine.add_transition(NOSTATE, DEPLOYING, 'active')

# A deployment may fail
machine.add_transition(DEPLOYING, DEPLOYFAIL, 'fail')

# A failed deployment may be retried
# ironic/conductor/manager.py:655
machine.add_transition(DEPLOYFAIL, DEPLOYING, 'rebuild')

# A deployment may also wait on external callbacks
machine.add_transition(DEPLOYING, DEPLOYWAIT, 'wait')
machine.add_transition(DEPLOYWAIT, DEPLOYING, 'resume')

# A deployment may complete
machine.add_transition(DEPLOYING, DEPLOYDONE, 'done')

# A completed deployment may be marked "active"
machine.add_transition(DEPLOYDONE, ACTIVE, 'next-state')

# An active instance may be re-deployed
# ironic/conductor/manager.py:655
machine.add_transition(ACTIVE, DEPLOYING, 'rebuild')

# An active instance may be deleted
# ironic/conductor/manager.py:757
machine.add_transition(ACTIVE, DELETING, 'delete')

# While a deployment is waiting, it may be deleted
# ironic/conductor/manager.py:757
machine.add_transition(DEPLOYWAIT, DELETING, 'delete')

# A failed deployment may also be deleted
# ironic/conductor/manager.py:757
machine.add_transition(DEPLOYFAIL, DELETING, 'delete')

# A delete may complete
machine.add_transition(DELETING, NOSTATE, 'done')

# Any state can also transition to error
machine.add_transition(NOSTATE, ERROR, 'error')
machine.add_transition(DEPLOYING, ERROR, 'error')
machine.add_transition(DEPLOYWAIT, ERROR, 'error')
machine.add_transition(ACTIVE, ERROR, 'error')
machine.add_transition(REBUILD, ERROR, 'error')
machine.add_transition(DELETING, ERROR, 'error')

# An errored instance can be rebuilt
# ironic/conductor/manager.py:655
machine.add_transition(ERROR, DEPLOYING, 'rebuild')
# or deleted
# ironic/conductor/manager.py:757
machine.add_transition(ERROR, DELETING, 'delete')


# Freeze the state machine; no more states can be added
machine.freeze()
