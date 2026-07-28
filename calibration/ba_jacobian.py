"""Analytic Jacobian for the bundle-adjustment objective in ``ba.py``.

Provides ``ba_jacobian(params, ...)`` with the SAME signature as ``ba.objfun``
so it can be passed as ``jac=`` to ``scipy.optimize.least_squares``. Replacing
the default finite-difference Jacobian removes the per-iteration eval explosion
(the reprojection block alone has 2·#observations rows) → typically 10-50x fewer
objective evaluations, with no loss of accuracy (an exact Jacobian is at least as
good as scipy's 2-point approximation).

Residual ordering matches ``ba.objfun`` exactly:
    [ NLL reprojection (2·#visible) | var3d (n_var3d) | varbone (B) ]

Parameter layout matches ``ba.to_theta`` / ``ba.from_theta``:
    [ rvec_0..rvec_{C-1} (3C) | t_0..t_{C-1} (3C) | X_0..X_{NJ-1} (3·N·J) ]

Blocks:
- NLL:     analytic (projection derivative ∘ Rodrigues derivative from cv2).
- varbone: analytic (d variance-of-bone-length / d point coords).
- var3d:   finite-difference over the 3C rotation-vector params only (cheap, exact
           to step precision; keeps ordering identical to objfun_var3d).
"""
import cv2
import numpy as np
from scipy.sparse import coo_matrix

from calibration.ba import objfun_var3d, objfun_varbone


def _nll_jac(params, K, ss2d, x, C, N, J, conf_threshold, obs_weight, n_cam):
    """Analytic Jacobian entries for the reprojection (NLL) block.

    Returns (rows, cols, vals, n_rows). Row order matches objfun_nll: per camera,
    per visible point (in flattened N*J order), residuals [ex, ey].
    """
    NJ = N * J
    mask = (ss2d > conf_threshold).reshape(C, NJ)
    s_all = ss2d.reshape(C, NJ)
    rows_all, cols_all, vals_all = [], [], []
    row = 0
    for c in range(C):
        Kc = K[c]
        rvec = params[3 * c:3 * c + 3]
        Rc, dRdr = cv2.Rodrigues(rvec)            # Rc (3,3); dRdr is (9,3) or (3,9)
        if dRdr.shape == (3, 9):
            dRdr = dRdr.T                         # normalize to (9,3): rows=R flat, cols=rvec
        tc = params[3 * C + 3 * c:3 * C + 3 * c + 3]
        fx, fy = Kc[0, 0], Kc[1, 1]

        vis = np.where(mask[c])[0]
        nv = len(vis)
        if nv == 0:
            continue
        Xw = x[vis]                                # (nv,3)
        Xc = Xw @ Rc.T + tc                        # (nv,3)
        z = Xc[:, 2]
        # weights (sqrt(2)*conf * optional obs_weight), as in objfun_nll
        w = np.sqrt(2.0) * s_all[c, vis]
        if obs_weight is not None:
            w = w * obs_weight[c, vis]

        # d y_hat / d Xc  (nv,2,3)
        Jp = np.zeros((nv, 2, 3))
        Jp[:, 0, 0] = fx / z
        Jp[:, 0, 2] = -fx * Xc[:, 0] / z ** 2
        Jp[:, 1, 1] = fy / z
        Jp[:, 1, 2] = -fy * Xc[:, 1] / z ** 2

        dyd_t = Jp                                  # d y_hat/d t  (nv,2,3)
        dyd_X = np.einsum('pij,jk->pik', Jp, Rc)    # d y_hat/d Xw (nv,2,3)
        # d(R Xw)/d r : M[p,a,k] = sum_b (dR/dr_k)[a,b] Xw[p,b]
        # dRdr is (9,3) with row index a*3+b -> reshape to (a,b,k)
        dR = dRdr.reshape(3, 3, 3)                  # (a, b, k)
        M = np.einsum('abk,pb->pak', dR, Xw)        # (nv,3,3)
        dyd_r = np.einsum('pij,pjk->pik', Jp, M)    # (nv,2,3)

        # residual e = (y_obs - y_hat)*w  ->  de/dθ = -w * dy_hat/dθ
        wf = w[:, None, None]
        blk_r = -wf * dyd_r
        blk_t = -wf * dyd_t
        blk_X = -wf * dyd_X

        # assemble COO: each point -> 2 rows (ex,ey) x 9 cols
        base_rows = row + 2 * np.arange(nv)
        col_r = 3 * c + np.arange(3)
        col_t = 3 * C + 3 * c + np.arange(3)
        col_X = n_cam + 3 * vis[:, None] + np.arange(3)   # (nv,3)
        for comp in range(2):                              # ex then ey
            rr = (base_rows + comp)
            # rvec cols (same 3 cols for all points of this cam)
            rows_all.append(np.repeat(rr, 3)); cols_all.append(np.tile(col_r, nv)); vals_all.append(blk_r[:, comp, :].ravel())
            rows_all.append(np.repeat(rr, 3)); cols_all.append(np.tile(col_t, nv)); vals_all.append(blk_t[:, comp, :].ravel())
            rows_all.append(np.repeat(rr, 3)); cols_all.append(col_X.ravel());       vals_all.append(blk_X[:, comp, :].ravel())
        row += 2 * nv
    return rows_all, cols_all, vals_all, row


def _varbone_jac(x, bone_idx, invalid_mask, lambda2, N, J, n_cam, row0):
    """Analytic Jacobian entries for the varbone block (B rows)."""
    bone_idx = np.asarray(bone_idx)
    B = len(bone_idx)
    xw = x.copy()
    xw[invalid_mask] = np.nan
    xw = xw.reshape(N, J, 3)
    rows_all, cols_all, vals_all = [], [], []
    for b in range(B):
        j1, j2 = int(bone_idx[b, 0]), int(bone_idx[b, 1])
        d = xw[:, j1, :] - xw[:, j2, :]            # (N,3)
        L = np.linalg.norm(d, axis=1)              # (N,), nan if endpoint nan
        valid = ~np.isnan(L) & (L > 1e-12)
        nb = int(valid.sum())
        if nb < 1:
            continue
        Lb = L[valid]
        Lbar = Lb.mean()
        u = d[valid] / L[valid][:, None]           # (nb,3) unit vectors
        # d var / d L_f = (2/nb)(L_f - Lbar); var uses ddof=0 (numpy nanvar default)
        coef = lambda2 * (2.0 / nb) * (Lb - Lbar)  # (nb,)
        g1 = coef[:, None] * u                     # d residual / d X[f,j1]  (nb,3)
        g2 = -g1                                   # d residual / d X[f,j2]
        fidx = np.where(valid)[0]
        col1 = n_cam + 3 * (fidx * J + j1)[:, None] + np.arange(3)   # (nb,3)
        col2 = n_cam + 3 * (fidx * J + j2)[:, None] + np.arange(3)
        r = np.full(nb * 3, row0 + b)
        rows_all.append(r); cols_all.append(col1.ravel()); vals_all.append(g1.ravel())
        rows_all.append(r); cols_all.append(col2.ravel()); vals_all.append(g2.ravel())
    return rows_all, cols_all, vals_all


def _var3d_jac_numeric(params, sp3d, ss3d, bone_idx, C, lambda1, n_var3d, row0, eps=1e-6):
    """Finite-difference Jacobian of the var3d block over the 3C rvec params only."""
    from calibration.ba import from_theta

    def var3d_of(p):
        R_w2c, _, _ = from_theta(p, C)
        return objfun_var3d(R_w2c, sp3d, (ss3d > 0), bone_idx) * lambda1

    f0 = var3d_of(params)
    rows_all, cols_all, vals_all = [], [], []
    for k in range(3 * C):                          # only rotation-vector params
        pp = params.copy(); pp[k] += eps
        df = (var3d_of(pp) - f0) / eps              # (n_var3d,)
        nz = np.where(np.abs(df) > 0)[0]
        if len(nz) == 0:
            continue
        rows_all.append(row0 + nz)
        cols_all.append(np.full(len(nz), k))
        vals_all.append(df[nz])
    return rows_all, cols_all, vals_all, len(f0)


def ba_jacobian(params, K, sp2d, ss2d, sp3d, ss3d, bone_idx, C, N, J,
                lambda1, lambda2, invalid_mask, conf_threshold=0.5, obs_weight=None):
    """Full analytic/hybrid Jacobian, matching ba.objfun's residual layout."""
    from calibration.ba import from_theta

    _, _, x = from_theta(params, C)
    NJ = N * J
    n_cam = 6 * C
    n_params = n_cam + 3 * NJ

    r1, c1, v1, n_nll = _nll_jac(params, K, ss2d, x, C, N, J, conf_threshold, obs_weight, n_cam)
    r3, c3, v3, n_var3d = _var3d_jac_numeric(params, sp3d, ss3d, bone_idx, C, lambda1,
                                             None, n_nll)
    r2, c2, v2 = _varbone_jac(x, bone_idx, invalid_mask, lambda2, N, J, n_cam,
                              n_nll + n_var3d)
    n_res = n_nll + n_var3d + len(np.asarray(bone_idx))

    rows = np.concatenate(r1 + r3 + r2) if (r1 or r3 or r2) else np.array([], int)
    cols = np.concatenate(c1 + c3 + c2) if (r1 or r3 or r2) else np.array([], int)
    vals = np.concatenate(v1 + v3 + v2) if (r1 or r3 or r2) else np.array([], float)
    return coo_matrix((vals, (rows, cols)), shape=(n_res, n_params)).tocsr()
