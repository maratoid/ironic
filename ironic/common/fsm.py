# -*- coding: utf-8 -*-

#    Copyright (C) 2014 Yahoo! Inc. All Rights Reserved.
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

try:
    from collections import OrderedDict  # noqa
except ImportError:
    from ordereddict import OrderedDict  # noqa

import six

from ironic.common import exception as excp


class _Jump(object):
    """A FSM transition tracks this data while jumping."""
    def __init__(self, name, on_enter, on_exit):
        self.name = name
        self.on_enter = on_enter
        self.on_exit = on_exit


class FrozenMachine(Exception):
    """Exception raised when a frozen machine is modified."""
    def __init__(self):
        super(FrozenMachine, self).__init__("Frozen machine can't be modified")


class FSM(object):
    """A finite state machine.

    This state machine can be used to automatically run a given set of
    transitions and states in response to events (either from callbacks or from
    generator/iterator send() values, see PEP 342). On each triggered event, a
    on_enter and on_exit callback can also be provided which will be called to
    perform some type of action on leaving a prior state and before entering a
    new state.

    NOTE(harlowja): reactions will *only* be called when the generator/iterator
    from run_iter() does *not* send back a new event (they will always be
    called if the run() method is used). This allows for two unique ways (these
    ways can also be intermixed) to use this state machine when using
    run_iter(); one where *external* events trigger the next state transition
    and one where *internal* reaction callbacks trigger the next state
    transition. The other way to use this state machine is to skip using run()
    or run_iter() completely and use the process_event() method explicitly and
    trigger the events via some *external* functionality.
    """
    def __init__(self, start_state=None):
        self._transitions = {}
        self._states = OrderedDict()
        self._start_state = start_state
        self._target_state = None
        self._current = None
        self.frozen = False

    @property
    def start_state(self):
        return self._start_state

    @property
    def current_state(self):
        if self._current is not None:
            return self._current.name
        return None

    @property
    def target_state(self):
        return self._target_state

    @property
    def terminated(self):
        """Returns whether the state machine is in a terminal state."""
        if self._current is None:
            return False
        return self._states[self._current.name]['terminal']

    def add_state(self, state, terminal=False, on_enter=None, on_exit=None, target=None):
        """Adds a given state to the state machine.

        The on_enter and on_exit callbacks, if provided will be expected to
        take two positional parameters, these being the state being exited (for
        on_exit) or the state being entered (for on_enter) and a second
        parameter which is the event that is being processed that caused the
        state transition.
        """
        if self.frozen:
            raise FrozenMachine()
        if state in self._states:
            raise excp.Duplicate("State '%s' already defined" % state)
        if on_enter is not None:
            assert six.callable(on_enter), "On enter callback must be callable"
        if on_exit is not None:
            assert six.callable(on_exit), "On exit callback must be callable"
        if target is not None and target not in self._states:
            raise excp.InvalidState("Target state '%s' does not exist"
                    % target)

        self._states[state] = {
            'terminal': bool(terminal),
            'reactions': {},
            'on_enter': on_enter,
            'on_exit': on_exit,
            'target': target,
        }
        self._transitions[state] = OrderedDict()

    def add_reaction(self, state, event, reaction, *args, **kwargs):
        """Adds a reaction that may get triggered by the given event & state.

        Reaction callbacks may (depending on how the state machine is ran) be
        used after an event is processed (and a transition occurs) to cause the
        machine to react to the newly arrived at stable state.

        These callbacks are expected to accept three default positional
        parameters (although more can be passed in via *args and **kwargs,
        these will automatically get provided to the callback when it is
        activated *ontop* of the three default). The three default parameters
        are the last stable state, the new stable state and the event that
        caused the transition to this new stable state to be arrived at.

        The expected result of a callback is expected to be a new event that
        the callback wants the state machine to react to. This new event
        may (depending on how the state machine is ran) get processed (and
        this process typically repeats) until the state machine reaches a
        terminal state.
        """
        if self.frozen:
            raise FrozenMachine()
        if state not in self._states:
            raise excp.NotFound("Can not add a reaction to event '%s' for an"
                                " undefined state '%s'" % (event, state))
        assert six.callable(reaction), "Reaction callback must be callable"
        if event not in self._states[state]['reactions']:
            self._states[state]['reactions'][event] = (reaction, args, kwargs)
        else:
            raise excp.Duplicate("State '%s' reaction to event '%s'"
                                 " already defined" % (state, event))

    def add_transition(self, start, end, event):
        """Adds an allowed transition from start -> end for the given event."""
        if self.frozen:
            raise FrozenMachine()
        if start not in self._states:
            raise excp.NotFound("Can not add a transition on event '%s' that"
                                " starts in a undefined state '%s'" % (event,
                                                                       start))
        if end not in self._states:
            raise excp.NotFound("Can not add a transition on event '%s' that"
                                " ends in a undefined state '%s'" % (event,
                                                                     end))
        self._transitions[start][event] = _Jump(end,
                                                self._states[end]['on_enter'],
                                                self._states[start]['on_exit'])

    def process_event(self, event):
        """Trigger a state change in response to the provided event."""
        current = self._current
        if current is None:
            raise excp.InvalidState("Can only process events after"
                                    " being initialized (not before)")
        if self._states[current.name]['terminal']:
            raise excp.InvalidState("Can not transition from terminal"
                                    " state '%s' on event '%s'"
                                    % (current.name, event))
        if event not in self._transitions[current.name]:
            raise excp.InvalidState("Can not transition from state '%s' on"
                                    " event '%s' (no defined transition)"
                                    % (current.name, event))
        replacement = self._transitions[current.name][event]
        if current.on_exit is not None:
            current.on_exit(current.name, event)
        if replacement.on_enter is not None:
            replacement.on_enter(replacement.name, event)
        self._current = replacement

        # clear _target if we've reached it
        if (self._target_state is not None and
                self._target_state == replacement.name):
            self._target_state = None
        # set target if there is a new one
        if (self._target_state is None and
                self._states[replacement.name]['target'] is not None):
            self._target_state = self._states[replacement.name]['target']

        return (
            self._states[replacement.name]['reactions'].get(event),
            self._states[replacement.name]['terminal'],
        )

    def test_event(self, event):
        """Check whether the event can be processed, but don't do it."""
        current = self._current
        if current is None:
            return False
        if self._states[current.name]['terminal']:
            return False
        if event not in self._transitions[current.name]:
            return False
        return True

    def initialize(self, state=None):
        """Sets up the state machine (sets current state to start state...)."""
        if state is None:
            state = self._start_state
        if state not in self._states:
            raise excp.NotFound("Can not start from a undefined"
                                " state '%s'" % (self._start_state))
        if self._states[self._start_state]['terminal']:
            raise excp.InvalidState("Can not start from a terminal"
                                    " state '%s'" % (self._start_state))
        self._current = _Jump(state, None, None)

    def run(self, event, initialize=True):
        """Runs the state machine, using reactions only."""
        for transition in self.run_iter(event, initialize=initialize):
            pass

    def copy(self, shallow=False):
        """Copies the current state machine (shallow or deep).

        NOTE(harlowja): the copy will be left in an *uninitialized* state.

        NOTE(harlowja): when a shallow copy is requested the copy will share
                        the same transition table and state table as the
                        source; this can be advantageous if you have a machine
                        and transitions + states that is defined somewhere
                        and want to use copies to run with (the copies have
                        the current state that is different between machines).
        """
        c = FSM(self.start_state)
        if not shallow:
            for state, data in six.iteritems(self._states):
                copied_data = data.copy()
                copied_data['reactions'] = copied_data['reactions'].copy()
                c._states[state] = copied_data
            for state, data in six.iteritems(self._transitions):
                c._transitions[state] = data.copy()
        else:
            c._transitions = self._transitions
            c._states = self._states
        return c

    def run_iter(self, event, initialize=True):
        """Returns a iterator/generator that will run the state machine.

        NOTE(harlowja): only one runner iterator/generator should be active for
        a machine, if this is not observed then it is possible for
        initialization and other local state to be corrupted and cause issues
        when running...
        """
        if initialize:
            self.initialize()
        while True:
            old_state = self.current_state
            reaction, terminal = self.process_event(event)
            new_state = self.current_state
            try:
                sent_event = yield (old_state, new_state)
            except GeneratorExit:
                break
            if terminal:
                break
            if reaction is None and sent_event is None:
                raise excp.NotFound("Unable to progress since no reaction (or"
                                    " sent event) has been made available in"
                                    " new state '%s' (moved to from state '%s'"
                                    " in response to event '%s')"
                                    % (new_state, old_state, event))
            elif sent_event is not None:
                event = sent_event
            else:
                cb, args, kwargs = reaction
                event = cb(old_state, new_state, event, *args, **kwargs)

    def __contains__(self, state):
        """Returns if this state exists in the machines known states."""
        return state in self._states

    def freeze(self):
        """Freezes & stops addition of states, transitions, reactions..."""
        self.frozen = True

    @property
    def states(self):
        """Returns the state names."""
        return list(six.iterkeys(self._states))

    @property
    def events(self):
        """Returns how many events exist."""
        c = 0
        for state in six.iterkeys(self._states):
            c += len(self._transitions[state])
        return c

    def __iter__(self):
        """Iterates over (start, event, end) transition tuples."""
        for state in six.iterkeys(self._states):
            for event, target in six.iteritems(self._transitions[state]):
                yield (state, event, target.name)
