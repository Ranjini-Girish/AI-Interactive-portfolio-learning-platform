# Thermodynamic Reference

This document summarizes the atmospheric thermodynamic quantities computed in the analysis pipeline.

## Saturation Vapor Pressure

The Buck (1981) equation is used for all saturation vapor pressure calculations. This equation provides improved accuracy over the older Magnus-Tetens formula, particularly at temperature extremes.

## Mixing Ratio

The mixing ratio w represents the mass of water vapor per unit mass of dry air. It differs from specific humidity q, which is the mass of water vapor per unit mass of moist air. The distinction matters at high humidity levels where the two quantities can differ by several percent.

## Virtual Temperature

The virtual temperature accounts for the buoyancy effect of water vapor in moist air. The exact formulation preserves the nonlinear relationship between moisture and density, while the commonly-used linear approximation introduces errors that compound through subsequent calculations.

## Potential Temperature

Potential temperature represents the temperature an air parcel would have if brought adiabatically to a reference pressure of 1000 hPa. It is conserved during dry adiabatic processes, making it useful for identifying air mass characteristics.

## Parcel Theory

Convective parameters (CAPE, CIN) are computed by comparing the virtual temperature of a lifted parcel with the environmental virtual temperature. The use of virtual temperature rather than dry temperature accounts for the buoyancy contribution of moisture.
