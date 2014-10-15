import time
import atexit
import threading
import Queue

from RPi import GPIO

class Stepper(threading.Thread):
    #half-steppipng pattern, also possible to skip every other for full-stepping
    pattern = [
        [1,0,0,0],
        [1,0,1,0],
        [0,0,1,0],
        [0,1,1,0],
        [0,1,0,0],
        [0,1,0,1],
        [0,0,0,1],
        [1,0,0,1]]

    def __init__(self, pin1=5, pin2=6, pin3=13, pin4=19, timeout=2):
        self.queue = Queue.Queue()
        self.finished = threading.Event()
        
        self.pins = [pin1, pin2, pin3, pin4]
        GPIO.setup(pin1, GPIO.OUT)
        GPIO.setup(pin2, GPIO.OUT)
        GPIO.setup(pin3, GPIO.OUT)
        GPIO.setup(pin4, GPIO.OUT)

        self.phase = 0
        self.timeout = timeout

    def stop(self):
        self.queue.put((None, None))

    def step(self, num, speed=10, block=False):
        """Step the stepper motor

        Parameters
        ----------
        num : int
            Number of steps
        speed : int
            Number of steps per second
        block : bool
            Block while stepping?
        """
        self.finished.clear()
        self.queue.put((num, speed))
        if block:
            self.finished.wait()

    def run(self):
        step, speed = self.queue.get()
        while step is not None:
            for pin, out in zip(self.pins, self.pattern[self.phase]):
                GPIO.output(pin, out)

            self._step(step, speed)
            self.finished.set()

            try:
                step, speed = self.queue.get(True, self.timeout)
            except Queue.Empty:
                #handle the timeout, turn off all pins
                for pin in self.pins:
                    GPIO.output(pin, False)
                step, speed = self.queue.get()

        for pin in self.pins:
            GPIO.output(pin, False)

    def _step(self, step, speed):
        steps = range(step)
        if step < 0:
            steps = range(step, 0)[::-1]

        for i in steps:
            now = time.time()
            output = self.pattern[(self.phase+i)%len(self.pattern)]
            for pin, out in zip(self.pins, output):
                GPIO.output(pin, out)

            diff = 1. / (2*speed) - (time.time() - now)
            if (diff) > 0:
                time.sleep(diff)
            
        self.phase += step


class Regulator(object):
    def __init__(self, maxsteps=3072, minsteps=1024, speed=10, ignite_pin=26):
        """Set up a stepper-controlled regulator. Implement some safety measures
        to make sure everything gets shut off at the end

        Parameters
        ----------
        maxsteps : int
            The max value for the regulator, in steps
        minsteps : int
            The minimum position to avoid extinguishing the flame
        speed : int
            Speed to turn the stepper, in steps per second
        ignite_pin : int or None
            If not None, turn on this pin during the ignite sequence
        """
        self.stepper = Stepper()
        self.stepper.start()
        self.current = 0
        self.max = maxsteps
        self.min = minsteps
        self.speed = speed
        self.lowthres = lowthres

        self.ignite_pin = ignite_pin
        if ignite_pin is not None:
            GPIO.setup(ignite_pin, OUT)

        atexit.register(self.off)

    def ignite(self, start=2048, delay=5):
        self.stepper.step(start, self.speed, block=True)
        if self.ignite_pin is not None:
            GPIO.output(self.ignite_pin, True)
        time.sleep(delay)
        if self.ignite_pin is not None:
            GPIO.output(self.ignite_pin, False)
        self.stepper.step(start - self.min, self.speed)
        self.current = start-stop

    def off(self, block=True):
        self.stepper.step(-self.current, self.speed, block=block)
        self.current = 0

    def set(self, value, block=True):
        if not 0 < value < 1:
            raise ValueError("Must give fraction between 0 and 1")
        target = value * (self.max - self.min) + self.min
        nsteps = target - self.current
        self.current = target
        self.stepper.step(nsteps, self.speed, block=block)