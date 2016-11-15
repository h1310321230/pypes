
# Description of the pipelines

- [Anatomical MRI (MPRAGE)](#anat)
- [FDG-PET](#fdg_pet)
- [MPRAGE + FDG-PET](#mrpet)
- [Resting-state fMRI](#fmri)
- [Independent Component Analysis](#ica)
- [Diffusion MRI](#dti)
- [Tractography](#tract)

## <a name="anat"></a> Anatomical MRI (MPRAGE)
This pipeline will clean and register a T1-weighted image to MNI.

It is based in ANTS and SPM12.
It is implemented in [`pypes.anat.attach_spm_anat_preprocessing`](https://github.com/Neurita/pypes/blob/master/pypes/anat.py).

1. Bias-field correction using ANTS/N4BiasFieldCorrection.
2. Brain tissue segmentation and spatial normalization with SPM12 New Segment.
3. Spatial normalization of tissues to MNI using SPM12 Normalize.
4. Create a brain mask based on tissue segmentations.

[optional]

5. Warp atlas (or any file in SPM12-MNI space) to anatomical space.

##### Related settings
```yaml
spm_dir: "~/Software/matlab_tools/spm12"

normalize_atlas: True
atlas_file: ''
```

## <a name="fdg_pet"></a> FDG-PET
This is a spatial normalization pipeline for FDG-PET images. Here I say specifically FDG-PET because I haven't tested
this too much for other PET tracers.

It is based on SPM12.
It is implemented in [`pypes.pet.warp.attach_spm_pet_preprocessing`](https://github.com/Neurita/pypes/blob/master/pypes/pet/warp.py).

1. Use SPM12 Normalize to spatially normalize FDG-PET to MNI.

There is a group-template option of this: first a group template
is created, then all FDG-PET are images are normalized to this
group template.

#### Related settings
```yaml
# GROUP PET TEMPLATE
spm_pet_grouptemplate_smooth.fwhm: 8
# path to a common PET template, if you don't want the average across subjects
spm_pet_grouptemplate.template_file: ""
```

## <a name="mrpet"></a> MPRAGE + FDG-PET
This is a partial volume correction and spatial normalization pipeline
for FDG-PET images.

It is based on PETPVC, nilearn and SPM12.
It is implemented in [`pypes.pet.mrpet.attach_spm_mrpet_preprocessing`](https://github.com/Neurita/pypes/blob/master/pypes/pet/mrpet.py).

This pipeline depends on the anatomical preprocessing pipeline.
There is 2 ways of doing the co-registration, you can configure that by
setting the `registration.anat2pet` boolean option to `True` or `False`.

#### If registration.anat2pet: True
1. Co-register anatomical and tissues to PET space.
2. Partial volume effect correction (PVC) with PETPVC in PET space.
This is done based on tissue segmentations from the anatomical pipeline.
3. Use SPM12 Normalize to normalize FDG-PET to MNI.

#### If registration.anat2pet: False
1. Co-register FDG-PET to anatomical space.
2. PVC with PETPVC in anatomical space.
3. Normalize PET to MNI with SPM12 Normalize applying the
anatomical-to-MNI warp field.

[optional]

5. Warp atlas from anatomical to PET space.

##### Related settings
```yaml
normalize_atlas: True
atlas_file: ''

registration.anat2pet: False

# GROUP PET TEMPLATE with MR co-registration
spm_mrpet_grouptemplate_smooth.fwhm: 8
spm_mrpet_grouptemplate.do_petpvc: True
# path to a common PET template, if you don't want the average across subjects
spm_mrpet_grouptemplate.template_file: ""

# PET PVC
rbvpvc.pvc: RBV
rbvpvc.fwhm_x: 4.3
rbvpvc.fwhm_y: 4.3
rbvpvc.fwhm_z: 4.3
```

## <a name="fmri"></a> Resting-state fMRI (RS-fMRI)
This pipeline preprocess fMRI data for resting-state fMRI analyses.
It depends on the MPRAGE preprocessing pipeline.

It is based on SPM12, nipype ArtifactDetect and TSNR, Nipy motion correction,
and nilearn.
It consists on two parts, the first is for data cleaning and the second for
warping and smoothing. The first is implemented in
[`pypes.fmri.clean.attach_fmri_cleanup_wf`](https://github.com/Neurita/pypes/blob/master/pypes/fmri/clean.py) and the latter is implemented in
[`pypes.fmri.warp.attach_spm_warp_fmri_wf`](https://github.com/Neurita/pypes/blob/master/pypes/fmri/warp.py). Both parts are connected and
are also prepared for create a common group template if you set that in the
configuration file. This connection is implemented in
[`pypes.fmri.rest._attach_rest_preprocessing`](https://github.com/Neurita/pypes/blob/master/pypes/fmri/rest.py).

1. Trim the first 6 seconds from the fMRI data.
2. Slice-time correction based on SPM12 SliceTiming.
This requires information in the headers of the files about acquisition
slice-timing. NifTI files generated from most DICOM formats with a recent
version of `dcm2niix` should have the necessary information.
3. Motion correction with nipy.SpaceTimeRealigner.
4. Co-registration of tissues in anatomical space to fMRI space.
5. Nuisance correction including time-course SNR (TSNR) estimation,
artifact detection (nipype.rapidART), motion estimation and filtering, signal
component regression from different tissues (nipype ACompCor) and global
signal regression (GSR).
These are configurable through the configuration file.
There is one thing that can't be easily modified is that, you need to
perform component regression for at least one tissue, e.g., CSF.
6. Bandpass time filter. Settings: `rest_input.lowpass_freq: 0.1`, and
`rest_input.highpass_freq: 0.01`.
7. Spatial smoothing. `smooth_fmri.fwhm: 8`

In the same way as for the MRI + FDG-PET pipeline, there is 2 ways for
registration. This is configured through the `registration.anat2fmri`
option.

#### If registration.anat2fmri: True
8. Cleaned-up versions of fMRI are directly warped to MNI using SPM12
Normalize.
9. Smooth these warped images, in the same ways as the non-warped data,
according to `smooth_fmri.fwhm: 8`.

#### If registration.anat2fmri: False
8. Co-register fMRI to anatomical space.
9. Apply the anat-to-MNI warp field to warp the cleaned-up versions of
the fMRI data to MNI.
10. Smooth these warped images, in the same ways as the non-warped data,
according to `smooth_fmri.fwhm: 8`.


##### Related settings
```yaml
registration.anat2fmri: True

# degree of b-spline used for rs-fmri interpolation
coreg_rest.write_interp: 3

## the last volume index to discard from the timeseries. default: 0
trim.begin_index: 5

# REST (COBRE DB)
# http://fcon_1000.projects.nitrc.org/indi/retro/cobre.html
# Rest scan:
# - collected in the Axial plane,
# - series ascending,
# - multi slice mode and
# - interleaved.
stc_input.slice_mode: alt_inc
stc_input.time_repetition: 2
#stc_input.num_slices: 33

# fMRI PREPROCESSING
fmri_warp.write_voxel_sizes: [2, 2, 2]
fmri_grptemplate_warp.write_voxel_sizes: [2, 2, 2]

# bandpass filter frequencies in Hz.
rest_input.lowpass_freq: 0.1 # the numerical upper bound
rest_input.highpass_freq: 0.01 # the numerical lower bound

# fwhm of smoothing kernel [mm]
smooth_fmri.fwhm: 8

## CompCor rsfMRI filters (at least compcor_csf should be True).
rest_filter.compcor_csf: True
rest_filter.compcor_wm: False
rest_filter.gsr: False

# filters parameters
## the corresponding filter must be enabled for these.

# motion regressors upto given order and derivative
# motion + d(motion)/dt + d2(motion)/dt2 (linear + quadratic)
motion_regressors.order: 0
motion_regressors.derivatives: 1

# number of polynomials to add to detrend
motart_parameters.detrend_poly: 2

# Compute TSNR on realigned data regressing polynomials up to order 2
tsnr.regress_poly: 2

# Threshold to use to detect motion-related outliers when composite motion is being used
detect_artifacts.use_differences: [True, False]
detect_artifacts.parameter_source: NiPy
detect_artifacts.mask_type: file
detect_artifacts.use_norm: True
detect_artifacts.zintensity_threshold: 3
detect_artifacts.norm_threshold: 1

# Number of principal components to calculate when running CompCor. 5 or 6 is recommended.
compcor_pars.num_components: 6

# Number of principal components to calculate when running Global Signal Regression. 1 is recommended.
gsr_pars.num_components: 1
```

## <a name="ica"></a> fMRI Independent Component Analysis (ICA)
This pipeline performs ICA on fMRI images. It is based on nilearn, and you
can choose between CanICA and DictLearning.
There is one version for one functional image, in `attach_canica` and
another
for a group ICA (GICA) in `attach_concat_canica`. However, probably the GICA
approach should be further tested on real data.

It depends on the RS-fMRI pipeline.
This is implemented in
[`pypes.postproc.decompose`](https://github.com/Neurita/pypes/blob/master/pypes/postproc/decompose.py).

##### Related settings
```yaml
# INDEPENDENT COMPONENTS ANALYSIS
## True to perform CanICA
rest_preproc.canica: False

# CanICA settings
canica.algorithm: 'canica' # choices: 'canica', 'dictlearning'
canica.do_cca: True
canica.standardize: True
canica.n_components: 20
canica.threshold: 2.0
canica.smoothing_fwhm: 8
#canica.random_state: 0

canica_extra.plot: True
canica_extra.plot_thr: 2.0 # used if threshold is not set in the ICA
```

## RS-fMRI Connectivity
**This pipeline is under development.**

This pipeline would need to warp an atlas file with the fMRI image, and then
perform the connectivity measures.
There is already an interface almost done in [`pypes.interfaces.nilearn.connectivity`](https://github.com/Neurita/pypes/blob/master/pypes/interfaces/nilearn/connectivity.py) for this.

##### Related settings
```yaml
normalize_atlas: True
atlas_file: ''

# RS-fMRI CONNECTIVITY
## if atlas_file is defined, perform connectivity analysis
rest_preproc.connectivity: True
## if further smoothing (remember the output of the rest workflow is already smoothed)
rest_connectivity.standardize: False
rest_connectivity.kind: correlation # choices: "correlation", "partial correlation", "tangent", "covariance", "precision".
rest_connectivity.smoothing_fwhm: 8
#rest_connectivity.resampling_target: # choices: "mask", "maps" or undefined.
rest_connectivity.atlas_type: labels # choices: "labels", "probabilistic".
```

## <a name="dti"></a> Diffusion MRI (DTI)
This pipeline performs Diffusion MRI correction and pre-processing., tensor-fitting and tractography
it is based on FSL Eddy, dipy, and UCL Camino.

1. Eddy currents and motion correction through FSL Eddy.
It needs certain fields in the NifTI file to be able to create input
parameters for Eddy. Any file converted from modern DICOM to NifTI with a
recent version of `dcm2nii` or `dcm2niix` should work.
2. Non-Local Means from dipy for image de-noising with a Rician filter.
3. Co-register the anatomical image to diffusion space.
4. Rotate the b-vecs based on motion estimation.

[optional]

5. Warp an atlas to diffusion space (needed if you'll perform tractography).

##### Related settings
```yaml
normalize_atlas: True
atlas_file: ''

# degree of b-spline used for interpolation
coreg_b0.write_interp: 3
nlmeans_denoise.N: 12 # number of channels in the head coil
```

## <a name="tract"></a> Tractography
This pipeline performs DTI tensor model fitting and tractography.

It is based on UCL Camino.
It depends on the MPRAGE and the DTI pipeline.

1. DTI fit.
2. ROIxROI atlas-based deterministic tractography.
3. Connectivity matrices: one with the number of tracts for each pair of
ROIs, the other with average tract FA values for each pair.

##### Related settings
```yaml
normalize_atlas: True
atlas_file: ''

# Camino Tractography
track.curvethresh: 50
track.anisthresh: 0.2
```