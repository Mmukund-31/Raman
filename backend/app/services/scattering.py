"""Light-scattering relations used for explanation and unit checks. None of this models the measured intensities in RamanReach.

Conventions
- Wavenumber (cm-1) = 1e7 / wavelength (nm), because 1 cm = 1e7 nm.
- Raman shift = wavenumber(excitation) - wavenumber(scattered). Stokes (scattered photon has LOWER energy, longer
  wavelength) gives a POSITIVE shift; anti-Stokes (HIGHER energy, shorter wavelength) gives a NEGATIVE shift. Some software
  reports anti-Stokes shifts as positive numbers on a separate axis; RamanReach keeps the sign.
"""
import math

NM_PER_CM = 1e7
C2_CM_K = 1.438777  # second radiation constant h*c/k_B in cm*K (CODATA 2018: 1.438 776 877... cm K)


def wavenumber_cm1(wavelength_nm: float) -> float:
    if wavelength_nm <= 0:
        raise ValueError("Wavelength must be positive.")
    return NM_PER_CM / wavelength_nm


def raman_shift_cm1(excitation_nm: float, scattered_nm: float) -> float:
    """Positive for Stokes (scattered_nm > excitation_nm), negative for anti-Stokes."""
    return wavenumber_cm1(excitation_nm) - wavenumber_cm1(scattered_nm)


def scattered_wavelength_nm(excitation_nm: float, shift_cm1: float) -> float:
    """Inverse of raman_shift_cm1. Shift must be smaller than the excitation wavenumber."""
    nu = wavenumber_cm1(excitation_nm) - shift_cm1
    if nu <= 0:
        raise ValueError("Raman shift must be smaller than the excitation wavenumber.")
    return NM_PER_CM / nu


def anti_stokes_to_stokes_ratio(shift_cm1: float, excitation_nm: float, temperature_K: float) -> float:
    """I_AS / I_S = ((nu0 + nu_k) / (nu0 - nu_k))^4 * exp(-h c nu_k / (k_B T)), nu_k = |shift| in cm-1.

    Assumes thermal equilibrium of the vibrational populations, identical detector response at both wavelengths, no
    resonance enhancement and no self-absorption. The exponential is the Boltzmann population ratio; the fourth power is the
    (nu0 -/+ nu_k)^4 frequency factor of the Raman intensity."""
    if temperature_K <= 0 or shift_cm1 <= 0:
        raise ValueError("Temperature and shift must be positive.")
    nu0 = wavenumber_cm1(excitation_nm)
    if shift_cm1 >= nu0:
        raise ValueError("Raman shift must be smaller than the excitation wavenumber.")
    return ((nu0 + shift_cm1) / (nu0 - shift_cm1)) ** 4 * math.exp(-C2_CM_K * shift_cm1 / temperature_K)


def rayleigh_sphere_intensity(i0: float, diameter: float, n_rel: float, wavelength: float, distance: float, theta_rad: float) -> float:
    """Rayleigh scattering by ONE small dielectric sphere, unpolarised incident light:

        I = I0 * (1 + cos^2 theta) / (2 R^2) * (2 pi / lambda)^4 * ((n^2 - 1) / (n^2 + 2))^2 * (d / 2)^6

    I0 incident irradiance; theta scattering angle (0 = forward); R distance from the particle; lambda wavelength in the
    medium; d particle diameter; n relative refractive index (particle / medium). `diameter`, `wavelength` and `distance`
    must share one length unit. Valid only for d << lambda and a non-absorbing particle. This is ELASTIC scattering: it
    changes direction, not wavelength, and is not the Raman intensity (which depends on the polarisability derivative of a
    specific vibration and on (nu0 - nu_k)^4)."""
    if min(diameter, wavelength, distance, i0) <= 0:
        raise ValueError("i0, diameter, wavelength and distance must be positive.")
    if diameter >= wavelength / 10:
        raise ValueError("Rayleigh formula requires diameter << wavelength (here: diameter < wavelength/10).")
    return (i0 * (1 + math.cos(theta_rad) ** 2) / (2 * distance ** 2) * (2 * math.pi / wavelength) ** 4
            * ((n_rel ** 2 - 1) / (n_rel ** 2 + 2)) ** 2 * (diameter / 2) ** 6)
