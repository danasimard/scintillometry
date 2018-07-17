# Licensed under the GPLv3 - see LICENSE

import numpy as np
from astropy.utils import lazyproperty


__all__ = ['FFTMakerBase', 'FFTBase', 'get_fft_maker']


FFT_MAKER_CLASSES = {}
"""Dict for storing FFT maker classes, indexed by their name or prefix."""


class FFTMakerMeta(type):
    """Registry of FFT maker classes.

    Registers classes using the `FFT_MAKER_CLASSES` dict, using a key
    generated by lowercasing the class's name and removing any trailing
    'fftmaker' (eg. the key for 'NumpyFFTMaker' is 'numpy').  The class
    automatically registers any subclass of `FFTMakerBase`, checking for key
    conflicts before registering.  Used by `get_fft_maker` to select classes.

    Users that wish to register their own FFT maker class should either
    subclass `FFTMakerBase` or use `FFTMakerMeta` as the metaclass.
    """
    _registry = FFT_MAKER_CLASSES

    def __init__(cls, name, bases, dct):

        # Ignore FFTMakerBase.
        if name != 'FFTMakerBase':

            # Extract name from class.
            key = name.lower()

            if key.endswith('fftmaker') and len(key) > 8:
                key = key[:-8]

            # Check if EDV is already registered.
            if key in FFTMakerMeta._registry:
                raise ValueError("key {0} already registered in "
                                 "FFT_MAKER_CLASSES.".format(key))

            FFTMakerMeta._registry[key] = cls

        super().__init__(name, bases, dct)


class FFTMakerBase(metaclass=FFTMakerMeta):
    """Base class for all FFT factories.

    Currently does not support Hermitian FFTs.
    """

    def get_data_format(self, time_data=None, freq_data=None, axis=0):
        """Extract time and frequency-domain array shape and dtype.

        Users may provide ``time_data``, ``freq_data``, or both.  If only
        ``freq_data`` is provided, data is assumed to be complex in the time
        domain.

        Parameters
        ----------
        time_data : `~numpy.ndarray`, dict, or None
            Dummy array with dimensions and dtype of time-domain data.  Can
            alternatively give a dict with 'shape' and 'dtype' entries.
            If not given, it is derived from ``freq_data``.
        freq_data : `~numpy.ndarray`, dict, or None
            Dummy array with dimensions and dtype of frequency-domain data.
            Can alternatively give a dict with 'shape' and 'dtype' entries.
            If not given, it is derived from ``time_data``.  If both are given,
            they will be checked for consistency.
        axis : int, optional
            Axis of transform.  Default: 0.

        Returns
        -------
        data_format : dict
            Dict of time and frequency-domain array shape and dtype.
        """

        if time_data is None and freq_data is None:
            raise TypeError("at least one of time or frequency-domain arrays "
                            "must be passed in.")

        # Extract information if user passed in dummy arrays.
        if isinstance(time_data, np.ndarray):
            time_data = {'shape': time_data.shape,
                         'dtype': time_data.dtype}
        elif isinstance(time_data, dict):
            if isinstance(time_data['dtype'], str):
                time_data['dtype'] = np.dtype(time_data['dtype'])

        if isinstance(freq_data, np.ndarray):
            freq_data = {'shape': freq_data.shape,
                         'dtype': freq_data.dtype}
        elif isinstance(freq_data, dict):
            if isinstance(freq_data['dtype'], str):
                freq_data['dtype'] = np.dtype(freq_data['dtype'])

        # If user passed in None for either array, create the other.
        if freq_data is None:
            # If data in time domain is real, calculate real data
            if time_data['dtype'].kind == 'f':
                freq_data = {
                    'shape': self.get_rft_freq_shape(time_data['shape'],
                                                     axis),
                    'dtype': np.dtype('c{0:d}'.format(
                        time_data['dtype'].itemsize * 2))}
            else:
                freq_data = time_data.copy()
        elif time_data is None:
            time_data = freq_data.copy()
        # If user passed both in, verify data formats and shapes are
        # self-consistent.
        else:
            fd = freq_data['dtype']
            fs = freq_data['shape']
            if time_data['dtype'].kind == 'f':
                fd_expected = np.dtype('c{0:d}'.format(
                    time_data['dtype'].itemsize * 2))
                fs_expected = self.get_rft_freq_shape(time_data['shape'], axis)
            else:
                fd_expected = time_data['dtype']
                fs_expected = time_data['shape']

            # dtype is more fundamental than shape, so check it first.
            assert fd is fd_expected, (
                "frequency dtype {fd} should be {fde} for a {cr} transform "
                "from time array with dtype {td}".format(
                    fd=fd, fde=fd_expected, cr=(
                        'complex' if time_data['dtype'].kind == 'c'
                        else 'real'), td=time_data['dtype']))
            assert fs == fs_expected, (
                "frequency array shape {fs} should be {fse} for a {cr} "
                "transform from time array with shape {ts}.".format(
                    fs=fs, fse=fs_expected, cr=(
                        'complex' if time_data['dtype'].kind == 'c'
                        else 'real'), ts=time_data['shape']))

        # Combine information into a single dict.
        data_format = {'time_shape': time_data['shape'],
                       'time_dtype': time_data['dtype'],
                       'freq_shape': freq_data['shape'],
                       'freq_dtype': freq_data['dtype']}

        return data_format

    @staticmethod
    def get_rft_freq_shape(time_shape, axis):
        """Get frequency-domain array shape for DFT of real-valued time data.

        Parameters
        ----------
        time_shape : tuple
            Time-domain array shape.
        axis : int
            Axis of transform.

        Returns
        -------
        freq_shape : tuple
        """
        freq_shape = list(time_shape)
        freq_shape[axis] = freq_shape[axis] // 2 + 1
        return tuple(freq_shape)

    def __call__(self, **kwargs):
        """Placeholder for FFT setup."""
        raise NotImplementedError()

    def fft(self, time_data=None, freq_data=None, axis=0, ortho=False,
            sample_rate=None):
        """Get forward FFT.

        Parameters are identical to those of ``__call__``.
        """
        FFT = self.__call__(time_data=time_data, freq_data=freq_data,
                            axis=axis, ortho=ortho,
                            sample_rate=sample_rate)
        return FFT(direction='forward')

    def ifft(self, time_data=None, freq_data=None, axis=0, ortho=False,
             sample_rate=None):
        """Get inverse FFT.

        Parameters are identical to those of ``__call__``.
        """
        FFT = self.__call__(time_data=time_data, freq_data=freq_data,
                            axis=axis, ortho=ortho,
                            sample_rate=sample_rate)
        return FFT(direction='inverse')


class FFTBase(object):
    """Framework for single pre-defined FFT and its associated metadata."""

    def __init__(self, direction):
        self._direction = direction if direction == 'inverse' else 'forward'

    @property
    def direction(self):
        """Direction of the FFT ('forward' or 'inverse')."""
        return self._direction

    @property
    def data_format(self):
        """Shapes and dtypes of the FFT arrays.

        'time' and 'freq' entries are for time and frequency-domain arrays,
        respectively.
        """
        return self._data_format

    @property
    def axis(self):
        """Axis over which to perform the FFT."""
        return self._axis

    @property
    def ortho(self):
        """Use orthogonal normalization.

        If `True`, both forward and backward transforms are scaled by
        1 / sqrt(n), where n is the size of time-domain array's transform
        axis.  If `False`, forward transforms are unscaled and inverse ones
        scaled by 1 / n.
        """
        return self._ortho

    @property
    def sample_rate(self):
        """Rate of samples in the time domain."""
        return self._sample_rate

    @lazyproperty
    def freq(self):
        """FFT sample frequencies.

        Uses `numpy.fft.fftfreq` for complex time-domain data, which returns,
        for an array of length n and a time-domain ``sample_rate``,

            f = [0, 1, ...,   n/2-1,     -n/2, ..., -1] * sample_rate / n

        if n is even, and

            f = [0, 1, ..., (n-1)/2, -(n-1)/2, ..., -1] * sample_rate / n

        if n is odd.

        For real time-domain data, `numpy.fft.rfftfreq` is used, which returns

            f = [0, 1, ...,     n/2-1,     n/2] * sample_rate / n

        if n is even, and

            f = [0, 1, ..., (n-1)/2-1, (n-1)/2] * sample_rate / n

        if n is odd.

        If ``sample_rate`` is `None`, output is unitless.

        Returns
        -------
        freqs : `~numpy.ndarray` or array of `~astropy.units.Quantity`
            Sample frequencies.
        """
        sample_rate = self.sample_rate
        if sample_rate is None:
            sample_rate = 1.
        a_length = self.data_format['time_shape'][self.axis]
        if 'float' in self.data_format['time_dtype'].name:
            return np.fft.rfftfreq(a_length, d=(1. / sample_rate))
        return np.fft.fftfreq(a_length, d=(1. / sample_rate))

    def __call__(self, a):
        """Perform FFT.

        To display the direction of the transform and shapes and dtypes of the
        arrays, use `print` or `repr`.

        Parameters
        ----------
        a : array_like
            Input data.

        Returns
        -------
        out : `~numpy.ndarray`
            Transformed data.
        """
        return self._fft(a)

    def inverse(self):
        """Return inverse transform.

        Returns
        -------
        inverse_transform : `~scintillometry.fourier.base.FFTBase` subclass
            Returns a new instance of the calling class with reversed transform
            direction.
        """
        return self.__class__(
            direction=('forward' if self.direction == 'inverse'
                       else 'inverse'))

    def copy(self):
        return self.__class__(direction=self.direction)

    def __copy__(self):
        return self.copy()

    def __eq__(self, other):
        # Assumes that class names are unique, which should be the case unless
        # the user improperly initializes the class factory.
        return (self.__class__.__name__ == other.__class__.__name__ and
                self.direction == other.direction and
                self.data_format == other.data_format and
                self.axis == other.axis and self.ortho == other.ortho and
                self.sample_rate == other.sample_rate)

    def __repr__(self):
        return ("<{s.__class__.__name__}"
                " direction={s.direction},\n"
                "    axis={s.axis}, ortho={s.ortho},"
                " sample_rate={s.sample_rate}\n"
                "    Time domain: shape={fmt[time_shape]},"
                " dtype={fmt[time_dtype]}\n"
                "    Frequency domain: shape={fmt[freq_shape]},"
                " dtype={fmt[freq_dtype]}>"
                .format(s=self, fmt=self.data_format))


def get_fft_maker(fft_engine, **kwargs):
    """FFT factory selector.

    Parameters
    ----------
    fft_engine : str
        Name of the FFT maker class (eg. 'numpy', 'pyfftw').
    **kwargs
        Additional keyword arguments for initializing the maker class
        (eg. ``n_simd`` for 'pyfftw').
    """
    return FFT_MAKER_CLASSES[fft_engine](**kwargs)