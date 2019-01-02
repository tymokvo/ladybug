# coding=utf-8
"""Utility functions for calculating PMV comfort."""
from __future__ import division

from ..rootfind import secant
from ..rootfind import bisect

import math


def pmv(ta, tr, vel, rh, met, clo, wme=0,
        still_air_threshold=0.1):
    """Calculate PMV using Fanger's original equation and Pierce SET model when necessary.

    This method is the officially corrent way to calculate PMV comfort according to.
    the 2015 ASHRAE-55 Thermal Comfort Standard.  This function will still return
    accurate values even if the air speed is above the sill air threshold of
    Fanger's original equation (0.1 m/s).

    Args:
        ta: air temperature [C]
        tr: mean radiant temperature [C]
        vel: relative air velocity [m/s]
        rh: relative humidity [%]
        met: metabolic rate [met]
        clo: clothing [clo]
        wme: external work [met], normally around 0 when seated
        still_air_threshold: The air velocity in m/s at which the Pierce
            Standard Effective Temperature (SET) model will be used
            to correct values in the original Fanger PMV model.
            Default is 0.1 m/s per the 2015 release of ASHRAE Standard-55.

    Returns:
        result: A dictionary containing results of the PMV model with the following keys:
            pmv : Predicted mean vote (PMV)
            ppd : Percent predicted dissatisfied (PPD) [%]
            set: The Standard effective temperature (SET) [C]
            ta_adj: Air temperature adjusted for air speed [C]
            ce : Cooling effect. The difference between the air temperature
                and the adjusted air temperature [C]
            heat_loss: A list with the 6 heat loss terms of the PMV model [W].
                The terms are ordered as follows:
                    * heat loss by conduction
                    * heat loss by sweating
                    * heat loss by latent respiration
                    * heat loss by dry respiration
                    * heat loss by radiation
                    * heat loss by convection

    References
    ----------
    [1] ASHRAE Standard 55 (2010). "Thermal Environmental Conditions
    for Human Occupancy".

    [2] Hoyt Tyler, Schiavon Stefano, Piccioli Alberto, Cheung Toby, Moon Dustin,
    and Steinfeld Kyle, 2017, CBE Thermal Comfort Tool. Center for the Built
    Environment, University of California Berkeley,
    http://comfort.cbe.berkeley.edu/

    [3] Doherty, T.J., and E.A. Arens.  (1988).  Evaluation of the physiological
    bases of thermal comfort models. ASHRAE Transactions, Vol. 94, Part 1, 15 pp.
    https://escholarship.org/uc/item/6pq3r5pr
    """

    result = {}
    set = pierce_set(ta, tr, vel, rh, met, clo, wme)

    if vel <= still_air_threshold:
        pmv, ppd, heat_loss = pmv_fanger(ta, tr, vel, rh, met, clo, wme)
        ta_adj = ta
        ce = 0
    else:
        ce_l = 0
        ce_r = 40
        eps = 0.001  # precision of ce

        def fn(ce):
            return (set - pierce_set(
                ta - ce, tr - ce,
                still_air_threshold, rh, met, clo, wme))

        ce = secant(ce_l, ce_r, fn, eps)
        if ce == 'NaN':
            ce = bisect(ce_l, ce_r, fn, eps, 0)

        pmv, ppd, heat_loss = pmv_fanger(
            ta - ce, tr - ce, still_air_threshold, rh, met, clo, wme)
        ta_adj = ta - ce

    result['pmv'] = pmv
    result['ppd'] = ppd
    result['set'] = set
    result['ta_adj'] = ta_adj
    result['ce'] = ce
    result['heat_loss'] = heat_loss

    return result


def pmv_fanger(ta, tr, vel, rh, met, clo, wme=0):
    """Calculate PMV using only Fanger's original equation.

    Note that Fanger's original expereiments were only conducted at
    low air speeds (<0.1 m/s) and the pmv() function above should be
    utilized in the case that air speeds may be higher than 0.1 m/s.

    Args:
        ta: air temperature [C]
        tr: mean radiant temperature [C]
        vel: relative air velocity [m/s]
        rh: relative humidity [%]
        met: metabolic rate [met]
        clo: clothing [clo]
        wme: external work [met], normally around 0 when seated

    Returns:
        pmv: predicted mean vote (PMV)
        ppd: percentage of people dissatisfied (PPD) [%]
        heat_loss: A list with the 6 heat loss terms of the PMV model [W].
            The terms are ordered as follows:
                * heat loss by conduction
                * heat loss by sweating
                * heat loss by latent respiration
                * heat loss by dry respiration
                * heat loss by radiation
                * heat loss by convection

    References
    ----------
    [1] Fanger, P.O. (1970). Thermal Comfort: Analysis and applications in environmental
    engineering. Copenhagen: Danish Technical Press.
    """

    pa = rh * 10 * math.exp(16.6536 - 4030.183 / (ta + 235))

    icl = 0.155 * clo  # thermal insulation of the clothing in M2K/W
    m = met * 58.15  # metabolic rate in W/M2
    w = wme * 58.15  # external work in W/M2
    mw = m - w  # internal heat production in the human body
    if (icl <= 0.078):
        fcl = 1 + (1.29 * icl)
    else:
        fcl = 1.05 + (0.645 * icl)

    # heat transf. coeff. by forced convection
    hcf = 12.1 * math.sqrt(vel)
    taa = ta + 273
    tra = tr + 273
    tcla = taa + (35.5 - ta) / (3.5 * icl + 0.1)

    p1 = icl * fcl
    p2 = p1 * 3.96
    p3 = p1 * 100
    p4 = p1 * taa
    p5 = (308.7 - 0.028 * mw) + (p2 * math.pow(tra / 100, 4))
    xn = tcla / 100
    xf = tcla / 50
    eps = 0.00015

    n = 0
    while abs(xn - xf) > eps:
        xf = (xf + xn) / 2
        hcn = 2.38 * math.pow(abs(100.0 * xf - taa), 0.25)
        if (hcf > hcn):
            hc = hcf
        else:
            hc = hcn
        xn = (p5 + p4 * hc - p2 * math.pow(xf, 4)) / (100 + p3 * hc)
        n += 1
        if (n > 150):
            print('Max iterations exceeded')
            return 1

    tcl = 100 * xn - 273

    # heat loss conduction through skin
    hl1 = 3.05 * 0.001 * (5733 - (6.99 * mw) - pa)
    # heat loss by sweating
    if mw > 58.15:
        hl2 = 0.42 * (mw - 58.15)
    else:
        hl2 = 0
    # latent respiration heat loss
    hl3 = 1.7 * 0.00001 * m * (5867 - pa)
    # dry respiration heat loss
    hl4 = 0.0014 * m * (34 - ta)
    # heat loss by radiation
    hl5 = 3.96 * fcl * (math.pow(xn, 4) - math.pow(tra / 100, 4))
    # heat loss by convection
    hl6 = fcl * hc * (tcl - ta)

    ts = 0.303 * math.exp(-0.036 * m) + 0.028
    pmv = ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)
    ppd = ppd_from_pmv(pmv)

    # collect heat loss terms.
    heat_loss = [hl1, hl2, hl3, hl4, hl5, hl6]

    return pmv, ppd, heat_loss


def pierce_set(ta, tr, vel, rh, met, clo, wme=0):
    """Calculate Standard Effective Temperature (SET) using the J.B. Pierce
    two-node model of human thermoregulation.

    Args:
        ta: air temperature [C]
        tr: mean radiant temperature [C]
        vel: relative air velocity [m/s]
        rh: relative humidity [%]
        met: metabolic rate [met]
        clo: clothing [clo]
        wme: external work [met], normally around 0 when seated

    Returns:
        set: standard effective temperature [C]

    References
    ----------
    [1] Nishi, Y; Gagge, A.P. (1977). "Effective temperature scale useful for
    hypo-and hyperbaric environments". Aviation, Space, and Environmental Medicine.
    48 (2): 97–107.
    """

    # Key initial variables.
    vapor_pressure = (rh * saturated_vapor_pressure_torr(ta)) / 100
    air_velocity = max(vel, 0.1)
    kclo = 0.25
    bodyweight = 69.9
    bodysurfacearea = 1.8258
    metfactor = 58.2
    sbc = 0.000000056697  # Stefan-Boltzmann constant (W/m2K4)
    csw = 170
    cdil = 120
    cstr = 0.5

    temp_skin_neutral = 33.7  # setpoint (neutral) value for Tsk
    temp_core_neutral = 36.49  # setpoint value for Tcr
    # setpoint for Tb (.1*temp_skin_neutral + .9*temp_core_neutral)
    temp_body_neutral = 36.49
    skin_blood_flow_neutral = 6.3  # neutral value for skin_blood_flow

    # INITIAL VALUES - start of 1st experiment
    temp_skin = temp_skin_neutral
    temp_core = temp_core_neutral
    skin_blood_flow = skin_blood_flow_neutral
    mshiv = 0.0
    alfa = 0.1
    esk = 0.1 * met

    # Start new experiment here (for graded experiments)
    # UNIT CONVERSIONS (from input variables)

    # This variable is the pressure of the atmosphere in kPa and was taken
    # from the psychrometrics.js file of the CBE comfort tool.
    p = 101325.0 / 1000

    pressure_in_atmospheres = p * 0.009869
    ltime = 60
    rcl = 0.155 * clo
    # Adjusticl(rcl, Conditions);  TH: I don't think this is used in the software

    facl = 1.0 + 0.15 * clo  # % INCreaSE IN BODY SURFACE Area DUE TO CLOTHING
    LR = 2.2 / pressure_in_atmospheres  # Lewis Relation is 2.2 at sea level
    RM = met * metfactor
    M = met * metfactor

    if clo <= 0:
        wcrit = 0.38 * pow(air_velocity, -0.29)
        icl = 1.0
    else:
        wcrit = 0.59 * pow(air_velocity, -0.08)
        icl = 0.45

    chc = 3.0 * pow(pressure_in_atmospheres, 0.53)
    chcV = 8.600001 * pow((air_velocity * pressure_in_atmospheres), 0.53)
    chc = max(chc, chcV)

    # initial estimate of Tcl
    chr = 4.7
    ctc = chr + chc
    RA = 1.0 / (facl * ctc)  # resistance of air layer to dry heat transfer
    top = (chr * tr + chc * ta) / ctc
    tcl = top + (temp_skin - top) / (ctc * (RA + rcl))

    # ========================  BEGIN ITERATION
    #
    # Tcl and chr are solved iteratively using: H(Tsk - To) = ctc(Tcl - To),
    # where H = 1/(Ra + Rcl) and Ra = 1/Facl*ctc

    tcl_old = tcl
    time = range(ltime)
    flag = True
    for TIM in time:
        if flag is True:
            while abs(tcl - tcl_old) > 0.01:
                tcl_old = tcl
                chr = 4.0 * sbc * pow(((tcl + tr) / 2.0 + 273.15), 3.0) * 0.72
                ctc = chr + chc
                # resistance of air layer to dry heat transfer
                RA = 1.0 / (facl * ctc)
                top = (chr * tr + chc * ta) / ctc
                tcl = (RA * temp_skin + rcl * top) / (RA + rcl)
        flag = False
        dry = (temp_skin - top) / (RA + rcl)
        hfcs = (temp_core - temp_skin) * (5.28 + 1.163 * skin_blood_flow)
        eres = 0.0023 * M * (44.0 - vapor_pressure)
        cres = 0.0014 * M * (34.0 - ta)
        scr = M - hfcs - eres - cres - wme
        ssk = hfcs - dry - esk
        tcsk = 0.97 * alfa * bodyweight
        tccr = 0.97 * (1 - alfa) * bodyweight
        dtsk = (ssk * bodysurfacearea) / (tcsk * 60.0)  # deg C per minute
        dtcr = scr * bodysurfacearea / (tccr * 60.0)  # deg C per minute
        temp_skin = temp_skin + dtsk
        temp_core = temp_core + dtcr
        TB = alfa * temp_skin + (1 - alfa) * temp_core
        sksig = temp_skin - temp_skin_neutral
        warms = (sksig > 0) * sksig
        colds = ((-1.0 * sksig) > 0) * (-1.0 * sksig)
        crsig = (temp_core - temp_core_neutral)
        warmc = (crsig > 0) * crsig
        coldc = ((-1.0 * crsig) > 0) * (-1.0 * crsig)
        bdsig = TB - temp_body_neutral
        warmb = (bdsig > 0) * bdsig
        skin_blood_flow = (skin_blood_flow_neutral + cdil *
                           warmc) / (1 + cstr * colds)
        if skin_blood_flow > 90.0:
            skin_blood_flow = 90.0
        if skin_blood_flow < 0.5:
            skin_blood_flow = 0.5
        regsw = csw * warmb * math.exp(warms / 10.7)
        if regsw > 500.0:
            regsw = 500.0
        ersw = 0.68 * regsw
        rea = 1.0 / (LR * facl * chc)  # evaporative resistance of air layer
        recl = rcl / (LR * icl)  # evaporative resistance of clothing (icl=.45)
        emax = (saturated_vapor_pressure_torr(
            temp_skin) - vapor_pressure) / (rea + recl)
        prsw = ersw / emax
        pwet = 0.06 + 0.94 * prsw
        edif = pwet * emax - ersw
        esk = ersw + edif
        if pwet > wcrit:
            pwet = wcrit
            prsw = wcrit / 0.94
            ersw = prsw * emax
            edif = 0.06 * (1.0 - prsw) * emax
            esk = ersw + edif
        if emax < 0:
            edif = 0
            ersw = 0
            pwet = wcrit
            prsw = wcrit
            esk = emax
        esk = ersw + edif
        mshiv = 19.4 * colds * coldc
        M = RM + mshiv
        alfa = 0.0417737 + 0.7451833 / (skin_blood_flow + .585417)

    # Define new heat flow terms, coeffs, and abbreviations
    hsk = dry + esk  # total heat loss from skin
    RN = M - wme  # net metabolic heat production
    ecomf = 0.42 * (RN - (1 * metfactor))
    if ecomf < 0.0:
        ecomf = 0.0  # from Fanger
    emax = emax * wcrit
    W = pwet
    pssk = saturated_vapor_pressure_torr(temp_skin)
    # Definition of ASHRAE standard environment... denoted "S"
    chrS = chr
    if met < 0.85:
        chcS = 3.0
    else:
        chcS = 5.66 * pow((met - 0.85), 0.39)
        if chcS < 3.0:
            chcS = 3.0

    ctcs = chcS + chrS
    rclos = 1.52 / ((met - wme / metfactor) + 0.6944) - 0.1835
    rcls = 0.155 * rclos
    facls = 1.0 + kclo * rclos
    fcls = 1.0 / (1.0 + 0.155 * facls * ctcs * rclos)
    ims = 0.45
    icls = ims * chcS / ctcs * (1 - fcls) / (chcS / ctcs - fcls * ims)
    ras = 1.0 / (facls * ctcs)
    reaS = 1.0 / (LR * facls * chcS)
    reclS = rcls / (LR * icls)
    hd_s = 1.0 / (ras + rcls)
    he_s = 1.0 / (reaS + reclS)

    # SET* (standardized humidity, clo, Pb, and chc)
    # determined using Newton's iterative solution
    # FNERRS is defined in the GENERAL SETUP section above

    delta = .0001
    dx = 100.0
    x_old = temp_skin - hsk / hd_s  # lower bound for SET
    while abs(dx) > .01:
        err1 = (hsk - hd_s * (temp_skin - x_old) - W * he_s *
                (pssk - 0.5 * saturated_vapor_pressure_torr(x_old)))
        err2 = (hsk - hd_s * (temp_skin - (x_old + delta)) - W * he_s *
                (pssk - 0.5 * saturated_vapor_pressure_torr((x_old + delta))))
        x = x_old - delta * err1 / (err2 - err1)
        dx = x - x_old
        x_old = x

    return x


def saturated_vapor_pressure_torr(db_temp):
    """Calculate saturated vapor pressure (Torr) at temperature (C)

    This is used to synchronize the results of the Standard Effective temperature (SET)
    model with the results of the original Fanger model.
    """
    return math.exp(18.6686 - 4030.183 / (db_temp + 235.0))


def ppd_from_pmv(pmv):
    """Calculate the Percentage of People Dissatisfied (PPD) from PMV.

    Args:
        pmv: The predicted mean vote (PMV) for which you want to know the PPD.

    Returns:
        ppd: The percentage of people dissatisfied (PPD) for the input PMV.
    """
    return 100.0 - 95.0 * math.exp(-0.03353 * pow(pmv, 4.0) - 0.2179 * pow(pmv, 2.0))


def pmv_from_ppd(ppd, ppd_error=0.001):
    """Calculate the two possible Predicted Mean Vote (PMV) values for a PPD value.

    Args:
        ppd: The percentage of people dissatisfied (PPD) for which you want to know
            the possible PMV.
        ppd_error: The acceptable error in meeting the target PPD.  Default = 0.001.

    Returns:
        pmv_lower: The lower (cold) PMV value that will produce the input ppd.
        pmv_upper: The upper (hot) PMV value that will produce the input ppd.
    """
    if ppd > 5 and ppd < 100:
        pmv_low = -3
        pmv_mid = 0
        pmv_hi = 3

        def fn(pmv):
            return (
                (100.0 - 95.0 *
                 math.exp(-0.03353 * pow(pmv, 4.0) - 0.2179 * pow(pmv, 2.0))) - ppd)

        # Solve for the missing lower PMV value.
        pmv_lower = secant(pmv_low, pmv_mid, fn, ppd_error)
        if pmv_lower == 'NaN':
            pmv_lower = bisect(pmv_low, pmv_mid, fn, ppd_error)
        # Solve for the missing higher PMV value.
        pmv_upper = secant(pmv_mid, pmv_hi, fn, ppd_error)
        if pmv_upper == 'NaN':
            pmv_upper = bisect(pmv_mid, pmv_hi, fn, ppd_error)

        return pmv_lower, pmv_upper
    else:
        raise ValueError(
            'PPD value {}% is outside acceptable limits of the PMV model.'.format(ppd))


def calc_missing_pmv_input(target_pmv, other_inputs,
                           missing_pmv_input='air temperature',
                           low_bound=0, up_bound=100, error=0.001):
    """Return the value of a missing_pmv_input given a target_pmv and the 6 other inputs.

    This is particularly useful when trying to draw comfort polygons on charts
    using the PMV model.

    Args:
        target_pmv: The target pmv that you are trying to produce from the inputs to
            this pmv object.
        other_inputs: A list of values for the other 6 inputs of the PMV model that
            are not the missing input. Values should be in the following order
            (skipping over the one that is the missing input):
                0 = air temperature
                1 = rad temperature
                2 = air speed
                3 = rel humidity
                4 = met rate
                5 = clo value
                6 = external work
        missing_pmv_input: Text representing which of the PMV inputs is missing and
            should be solved for.  Choose from the following options:
                air temperature
                rad temperature
                air speed
                rel humidity
                met rate
                clo value
                external work
        low_bound: The lowest possible value of the missing_input you are tying to
            find. Putting in a good value here will help the model converge to a
            solution faster.
        up_bound: The highest possible value of the missing_input you are tying to
            find. Putting in a good value here will help the model converge to a
            solution faster.
        error: The acceptable error in the target_pmv. The default is set to 0.001

    Returns:
        missing_val: The value of the missing_input that will produce the target_pmv.

    """
    missing_pmv_input = missing_pmv_input.lower()

    # Determine the function that should be used given the missing_pmv_input.
    if missing_pmv_input == 'air temperature':
        def fn(x):
            return (pmv(x, other_inputs[0], other_inputs[1],
                        other_inputs[2], other_inputs[3], other_inputs[4],
                        other_inputs[5])['pmv'] - target_pmv)
    elif missing_pmv_input == 'rad temperature':
        def fn(x):
            return (pmv(other_inputs[0], x, other_inputs[1],
                        other_inputs[2], other_inputs[3], other_inputs[4],
                        other_inputs[5])['pmv'] - target_pmv)
    elif missing_pmv_input == 'air speed':
        def fn(x):
            return (pmv(other_inputs[0], other_inputs[1], x,
                        other_inputs[2], other_inputs[3], other_inputs[4],
                        other_inputs[5])['pmv'] - target_pmv)
    elif missing_pmv_input == 'rel humidity':
        def fn(x):
            return (pmv(other_inputs[0], other_inputs[1], other_inputs[2],
                        x, other_inputs[3], other_inputs[4],
                        other_inputs[5])['pmv'] - target_pmv)
    elif missing_pmv_input == 'met rate':
        def fn(x):
            return (pmv(other_inputs[0], other_inputs[1], other_inputs[2],
                        other_inputs[3], x, other_inputs[4],
                        other_inputs[5])['pmv'] - target_pmv)
    elif missing_pmv_input == 'clo value':
        def fn(x):
            return (pmv(other_inputs[0], other_inputs[1], other_inputs[2],
                        other_inputs[3], other_inputs[4], x,
                        other_inputs[5])['pmv'] - target_pmv)
    elif missing_pmv_input == 'external work':
        def fn(x):
            return (pmv(other_inputs[0], other_inputs[1], other_inputs[2],
                        other_inputs[3], other_inputs[4],
                        other_inputs[5], x)['pmv'] - target_pmv)

    # Solve for the missing input using the function.
    missing_val = secant(low_bound, up_bound, fn, error)
    if missing_val == 'NaN':
        missing_val = bisect(low_bound, up_bound, fn, error)

    return missing_val
