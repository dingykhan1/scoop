#
#    This file is part of Scalable COncurrent Operations in Python (SCOOP).
#
#    SCOOP is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of
#    the License, or (at your option) any later version.
#
#    SCOOP is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with SCOOP. If not, see <http://www.gnu.org/licenses/>.
#
from __future__ import print_function
from collections import namedtuple
import control
from .types import Task
import greenlet
import scoop

# Constants stated by PEP 3148 (http://www.python.org/dev/peps/pep-3148/#module-functions)
ALL_COMPLETED = 0
FIRST_COMPLETED = 1
FIRST_EXCEPTION = 2

# This is the greenlet for running the controller logic.
_controller = None

def startup(rootTask, *args, **kargs):
    """This function initializes the SCOOP environment.
    
    :param rootTask: Any callable object (function or class object with __call__
        method); this object will be called once and allows the use of parallel
        calls inside this object.
    :param args: A tuple of positional arguments that will be passed to the 
        callable object. 
    :param kargs: A tuple of iterable objects; each will be zipped to form an
        iterable of arguments tuples that will be passed to the callable object
        as a separate task. 
        
    :returns: The result of the root task.
    
    Be sure to launch your root task using this method."""
    global _controller
    _controller = greenlet.greenlet(control.runController)
    try:
        result = _controller.switch(rootTask, *args, **kargs)
    except scoop.comm.Shutdown:
        return None
    return result
    
def shutdown(wait=True):
    """Signal SCOOP that it should free any resources that it is using when the
    currently pending futures are done executing. Calls to ``submit``, ``map`` 
    or any other futures method made after shutdown will raise RuntimeError.

    Regardless of the value of wait, the entire Python program will not exit
    until all pending futures are done executing.
    
    :param wait: If True, this method will be blocking, meaning that it will not
        return until all the pending futures are done executing and the
        resources associated with the executor have been freed. If wait is
        False, this method will return immediately and the resources associated
        with the executor willbe freed when all pending futures are done
        executing."""
    # TODO
    pass

def mapSubmit(callable, *iterables, **kargs):
    """This function is similar to the built-in map function, but each of its 
    iteration will spawn a separate independent parallel task that will run 
    either locally or remotely as `callable(*args, **kargs)`.
    
    :param callable: Any callable object (function or class object with __call__
        method); this object will be called to execute each task. 
    :param iterables: A tuple of iterable objects; each will be zipped
        to form an iterable of arguments tuples that will be passed to the
        callable object as a separate task. 
    :param kargs: A dictionary of additional keyword arguments that will be 
        passed to the callable object. 
        
    :returns: A list of task objects, each corresponding to an iteration of map.
    
    On return, the tasks are pending execution locally, but may also be
    transfered remotely depending on global load. Execution may be carried on
    with any further computations. To retrieve the map results, you need to
    either wait for or join with the spawned tasks. See functions waitAny,
    waitAll, or joinAll. Alternatively, You may also use functions mapWait or
    mapJoin that will wait or join before returning."""
    childrenList = []
    for args in zip(*iterables):
        childrenList.append(submit(callable, *args, **kargs))
    return childrenList

def map(callable, *iterables, **kargs):
    """This function is a helper function that simply calls joinAll on the 
    result of mapSubmit. It returns with a list of the map results, one for
    every iteration of the map.
    
    :param callable: Any callable object (function or class object with __call__
        method); this object will be called to execute each task. 
    :param iterables: A tuple of iterable objects; each will be zipped
        to form an iterable of arguments tuples that will be passed to the
        callable object as a separate task. 
    :param kargs: A dictionary of additional keyword arguments that will be 
        passed to the callable object. 
        
    :returns: A list of map results, each corresponding to one map iteration."""
    return joinAll(*mapSubmit(callable, *iterables, **kargs))

def mapWait(callable, *iterables, **kargs):
    """This function is a helper function that simply calls waitAll on the 
    result of mapSubmit. It returns with a generator function for the map
    results, one result for every iteration of the map.
    
    :param callable: Any callable object (function or class object with __call__
        method); this object will be called to execute the tasks. 
    :param iterables: A tuple of iterable objects; each will be zipped
        to form an iterable of arguments tuples that will be passed to the
        callable object as a separate task. 
    :param kargs: A dictionary of additional keyword arguments that will be 
        passed to the callable object. 
        
    :returns: A generator of map results, each corresponding to one map 
        iteration."""
    return waitAll(*mapSubmit(callable, *iterables, **kargs))

def submit(callable, *args, **kargs):
    """This function is for submitting an independent parallel task that will 
    either run locally or remotely as `callable(*args, **kargs)`.
    
    :param callable: Any callable object (function or class object with __call__
        method); this object will be called to execute the task. 
    :param args: A tuple of positional arguments that will be passed to the 
        callable object. 
    :param kargs: A dictionary of additional keyword arguments that will be 
        passed to the callable abject. 
        
    :returns: A future object for retrieving the task result.
    
    On return, the task is pending execution locally, but may also be transfered
    remotely depending on load. or on remote distributed workers. You may carry
    on with any further computations while the task completes. To retrieve the
    task result, you need to either wait for or join with the parallel task. See
    functions waitAny or join."""
    child = Task(control.current.id, callable, *args, **kargs)
    control.execQueue.append(child)
    return child

def waitAny(*children):
    """This function is for waiting on any child task created by the calling 
    task.
    
    :param children: A tuple of children task objects spawned by the calling 
        task.
        
    :return: A generator function that iterates on (index, result) tuples.
    
    The generator produces two-element tuples. The first element is the index of
    a result, and the second is the result itself. The index corresponds to the
    index of the task in the children argument. Tuples are generated in a non
    deterministic order that depends on the particular parallel execution of the
    tasks. The generator returns a tuple as soon as one becomes available. Any
    number of children tasks can be specified, for example just one, all of
    them, or any subset of created tasks, but they must have been spawned by the 
    calling task (using map or submit). See also waitAll for an alternative 
    option."""
    n = len(children)
    # check for available results and index those unavailable
    for index, task in enumerate(children):
        if task.result:
            yield task.result
            n -= 1
        else:
            task.index = index
    task = control.current
    while n > 0:
        # wait for remaining results; switch to controller
        task.stopWatch.halt()
        result = _controller.switch(task)
        task.stopWatch.resume()
        yield result
        n -= 1

def waitAll(*children):
    """This function is for waiting on all child tasks specified by a tuple of 
    previously created task (using map or submit).
    
    :param children: A tuple of children task objects spawned by the calling 
        task.
        
    :return: A generator function that iterates on task results.
    
    The generator produces results in the order that they are specified by
    the children argument. Because task are executed in a non deterministic 
    order, the generator may have to wait for the last result to become 
    available before it can produce an output. See waitAny for an alternative 
    option."""
    for index, task in enumerate(children):
        for result in waitAny(task):
            yield result

DoneAndNotDoneFutures = namedtuple('DoneAndNotDoneFutures', 'done not_done')
def wait(fs, timeout=None, return_when=ALL_COMPLETED):
    """Wait for the futures in the given sequence to complete.
    
    :param fs: The sequence of Futures (possibly created by another instance) to
        wait upon.
    :param timeout: The maximum number of seconds to wait. If None, then there
        is no limit on the wait time.
    :param return_when: Indicates when this function should return. The options
        are:
        
            FIRST_COMPLETED - Return when any future finishes or is
                              cancelled.
            FIRST_EXCEPTION - Return when any future finishes by raising an
                              exception. If no future raises an exception
                              then it is equivalent to ALL_COMPLETED.
            ALL_COMPLETED -   Return when all futures finish or are cancelled.
        
    :return: A named 2-tuple of sets. The first set, named 'done', contains the
        futures that completed (is finished or cancelled) before the wait
        completed. The second set, named 'not_done', contains uncompleted
        futures."""
    if return_when == FIRST_COMPLETED:
        waitAny(*fs)
    elif return_when == ALL_COMPLETED:
        waitAll(*fs)
    elif return_when == FIRST_EXCEPTION:
        while f in fs:
            # TODO Add exception handling
            waitAny(*f)
    done = set(f for f in fs \
        if scoop.control.dict.get(f.id, {}).get('result', None) != None)
    not_done = set(fs) - done
    return DoneAndNotDoneFutures(done, not_done)

def as_completed(fs, timeout=None):
    """An iterator over the given futures that yields each as it completes.

    :param fs: The sequence of Futures (possibly created by another instance) to
        wait upon.
    :param timeout: The maximum number of seconds to wait. If None, then there
        is no limit on the wait time.

    :return: An iterator that yields the given Futures as they complete
        (finished or cancelled).

    :raises:
        TimeoutError: If the entire result iterator could not be generated
            before the given timeout.
    """
    # TODO: Add timeout
    return waitAny(*fs)

def join(child):
    """This function is for joining the current task with one of its child 
    task.
    
    :param child: A child task object spawned by the calling task.
    
    :return: The result of the child task.
    
    Only one task can be specified. The function returns a single corresponding 
    result as soon as it becomes available."""
    for result in waitAny(child):
        return result

def joinAll(*children):
    """This function is for joining the current task with all of the children 
    tasks specified in a tuple.
    
    :param children: A tuple of children task objects spawned by the calling 
        task.
        
    :return: A list of corresponding results for the children tasks.
    
    This function will wait for the completion of all specified child tasks 
    before returning to the caller."""
    return [result for result in waitAll(*children)]