# -*- coding: utf-8 -*-
"""
Nipype registration nodes and workflows
"""
import nipype.interfaces.afni as afni
import nipype.interfaces.fsl as fsl
import nipype.interfaces.spm  as spm
import nipype.pipeline.engine    as pe
from   nipype.algorithms.misc    import Gunzip
from   nipype.interfaces.base import traits
from   nipype.interfaces.utility import IdentityInterface, Function, isdefined

from ..interfaces.nilearn import mean_img, concat_imgs
from .spatial import get_bounding_box
from ..config import setup_node
from ..utils import spm_tpm_priors_path


def spm_apply_deformations(in_imgs=traits.Undefined,
                           trans_field=traits.Undefined,
                           bbox=traits.Undefined,
                           voxel_sizes=None):
    """Return a Normalize12 interface object.
    SPM12's new Normalise routine for warping an image to a template.
    For more info:
    http://www.mit.edu/~satra/nipype-nightly/interfaces/generated/nipype.interfaces.spm.preprocess.html#normalize12

    Parameters
    ----------
    in_imgs: iterable of str

    trans_field: file
        file y_*.nii containing 3 deformation fields for the deformation in
        x, y and z dimension

    bbox: (a list of from 2 to 2 items which are a list of
           from 3 to 3 items which are a float)
        write_bounding_box option.
        3x2-element list of lists representing the bounding box (in mm) to
        be written
        See the preproc.get_bounding_box function.
        This is important to set when applying deformation fields
        to cropped images.

    voxel_sizes: list of 3 ints or floats
        Default: [1, 1, 1]

    Nipype Ouputs
    -------------
    deformation_field: (a list of items which are an existing file name)
        NIfTI file containing 3 deformation fields for the deformation in x,
        y and z dimension

    normalized_files: (a list of items which are an existing file name)
        Normalized other files

    normalized_image: (a list of items which are an existing file name)
        Normalized file that needed to be aligned

    """
    if voxel_sizes is None:
        voxel_sizes = [1, 1, 1]

    norm12 = spm.Normalize12(jobtype='write')

    norm12.inputs.deformation_file   = trans_field
    norm12.inputs.image_to_align     = in_imgs
    norm12.inputs.write_voxel_sizes  = voxel_sizes
    norm12.inputs.write_bounding_box = bbox

    #norm12.run()
    return norm12


def spm_normalize(in_imgs=traits.Undefined, template=None, **kwargs):
    """Return a Normalize12 interface object.
    SPM12's new Normalise routine for warping an image to a template.

    Parameters
    ----------
    in_imgs: iterable of str

    template: str
        Template in form of tissue probablitiy maps to normalize to
        mutually_exclusive: deformation_file.
        Default: the SPM TPM file.

    Nipype Ouputs
    -------------
    deformation_field: (a list of items which are an existing file name)
        NIfTI file containing 3 deformation fields for the deformation in x,
        y and z dimension

    normalized_files: (a list of items which are an existing file name)
        Normalized other files

    normalized_image: (a list of items which are an existing file name)
        Normalized file that needed to be aligned

    Raises
    ------
    FileNotFoundError
        If `template` is `None` and can't find the TPM.nii file from SPM.

    Notes
    -----
    For more info:
    http://www.mit.edu/~satra/nipype-nightly/interfaces/generated/nipype.interfaces.spm.preprocess.html#normalize12
    """
    if template is None:
        template = spm_tpm_priors_path()

    norm12 = spm.Normalize12(jobtype='estwrite',
                             tpm=template,
                             **kwargs)

    if isdefined(in_imgs):
        norm12.inputs.image_to_align = in_imgs

    #norm12.run()
    return norm12


def spm_coregister(src_img=traits.Undefined, tgt_img=traits.Undefined, cost_function='mi'):
    """Use spm_coreg for estimating cross-modality rigid body alignment.
    The write_interp option is set to 0 by default.

    More info: http://www.fil.ion.ucl.ac.uk/spm/doc/manual.pdf#page=39
    Parameters
    ----------
    src_img: str
        Path to the coregistration source image

    tgt_img: str
        Path to the coregistration target image

    cost_function: ('mi' or 'nmi' or 'ecc' or 'ncc')
        cost function, one of: 'mi' - Mutual Information,
         'nmi' - Normalised Mutual Information,
         'ecc' - Entropy Correlation Coefficient,
         'ncc' - Normalised Cross Correlation

        For more info:
        http://www.mit.edu/~satra/nipype-nightly/interfaces/generated/nipype.interfaces.spm.preprocess.html#coregister

    Returns
    -------
    coreg: nipype.interfaces.smp.Coregister
        spm.Coregister interface object
    """
    coreg = spm.Coregister()

    coreg.inputs.source = src_img
    coreg.inputs.target = tgt_img

    coreg.inputs.cost_function = cost_function
    coreg.inputs.jobtype = 'estwrite'

    #coreg.run()
    return coreg


def afni_deoblique(in_file=traits.Undefined, out_file=traits.Undefined, out_type='NIFTI_GZ'):
    """ Return a nipype interface for AFNI '3dWarp -deoblique'.

    Parameters
    ----------
    in_file: str
        Path to the input file

    out_file: str
        Path to the output file.

    out_type: str
        ('NIFTI_GZ' or 'AFNI' or 'NIFTI')
        AFNI output filetype

    Returns
    -------
    deob: nipype.interfaces.afni.Warp
    """

    deob = afni.Warp()
    deob.inputs.in_file = in_file
    deob.inputs.deoblique = True
    deob.inputs.out_file = out_file
    deob.inputs.outputtype = out_type

    return deob


def spm_create_group_template_wf(wf_name="spm_create_group_template"):
    """ Pick all subject files in `grptemplate_input.in_files`, calculate an average
    image and smooth it with `"{}_smooth".format(wf_name)` node (you can configure the smooth `fwhm` from
    a config file.).

    It does:
    - calculate a mean image (across subjects) and
    - smooth it with a 8x8x8mm^3 gaussian kernel -> the result of this is the template.
    The size of the isometric smoothing gaussian kernel is given by one integer for the
    "{}_smooth".format(wf_name) setting.

    Parameters
    ----------
    wf_name: str
        Name of the workflow.

    Nipype Inputs
    -------------
    grptemplate_input.in_files: list of traits.File
        The raw NIFTI_GZ PET image files

    Nipype outputs
    --------------
    grptemplate_output.template: existing file
        The common custom PET template file.

    Returns
    -------
    wf: nipype Workflow
    """
    # input
    input = setup_node(IdentityInterface(fields=["in_files"]), name="grptemplate_input",)

    # merge
    concat = setup_node(Function(function=concat_imgs,
                                 input_names=["in_files"],
                                 output_names=["out_file"],
                                 imports=['from pypes.interfaces.nilearn import ni2file']),
                        name='merge_time')

    # average
    average = setup_node(Function(function=mean_img,
                                  input_names=["in_file", "out_file"],
                                  output_names=["out_file"],
                                  imports=['from pypes.interfaces.nilearn import ni2file']),
                        name='average')
    average.inputs.out_file = 'group_average.nii.gz'

    # smooth
    #smooth = setup_node(Function(function=smooth_img,
    #                             input_names=["in_file", "fwhm"],
    #                             output_names=["out_file"],
    #                             imports=['from pypes.interfaces.nilearn import ni2file']),
    #                     name="{}_smooth".format(wf_name))
    smooth = setup_node(fsl.IsotropicSmooth(fwhm=8), name="{}_smooth".format(wf_name))

    # output
    output = setup_node(IdentityInterface(fields=["template"]), name="grptemplate_output",)

    # Create the workflow object
    wf = pe.Workflow(name=wf_name)

    wf.connect([
                # input
                (input,       concat,  [("in_files", "in_files")]),

                # merge, average and smooth
                (concat,      average, [("out_file", "in_file")]),
                (average,     smooth,  [("out_file", "in_file")]),

                # output
                (smooth,     output,   [("out_file", "template")]),
               ])

    return wf


def spm_register_to_template_wf(wf_name="spm_registration_to_template"):
    """Return a workflow that registers each reg_input.in_file to the file in reg_input.template.
    For now this does not do atlas registration.

    It does:
    - SPM12 Warp input image to the given template

    Parameters
    ----------
    wf_name: str
        Name of the workflow.

    Nipype Inputs
    -------------
    reg_input.in_file: traits.File
        The raw NIFTI_GZ subject image file.

    reg_input.template: list of traits.File
        The template file for inter-subject registration reference.

    Nipype outputs
    --------------
    reg_output.warped: existing file
        Image normalized to the given template.

    reg_output.warp_field: existing files
        Spatial normalization parameters .mat file.

    Returns
    -------
    wf: nipype Workflow
    """
    # specify input and output fields
    in_fields  = ["in_file",
                  "template",]

    out_fields = ["warped",
                  "warp_field",]

    # input
    reg_input = setup_node(IdentityInterface(fields=in_fields, mandatory_inputs=True),
                           name="reg_input")

    # warp each subject to the group template
    gunzip_template = setup_node(Gunzip(), name="gunzip_template",)
    gunzip_input    = setup_node(Gunzip(), name="gunzip_input",)

    warp2template = setup_node(spm.Normalize(jobtype="estwrite", out_prefix="wgrptemplate_"),
                               name="warp2template")

    get_bbox = setup_node(Function(function=get_bounding_box,
                                   input_names=["in_file"],
                                   output_names=["bbox"]),
                          name="get_bbox")

    # output
    reg_output = setup_node(IdentityInterface(fields=out_fields), name="reg_output")

    # Create the workflow object
    wf = pe.Workflow(name=wf_name)

    wf.connect([
                # get template bounding box to apply to results
                (reg_input,     get_bbox,        [("template", "in_file")]),

                # gunzip some inputs
                (reg_input,     gunzip_input,    [("in_file",  "in_file")]),
                (reg_input,     gunzip_template, [("template", "in_file")]),

                # prepare the target parameters of the warp to template
                (gunzip_template, warp2template, [("out_file", "template")]),
                (get_bbox,        warp2template, [("bbox",     "write_bounding_box")]),

                # directly warp pet to the template
                (gunzip_input,    warp2template, [("out_file", "source")]),

                # output
                (warp2template, reg_output, [("normalization_parameters", "warp_field"),
                                             ("normalized_source",        "warped"),
                                             ]),
               ])

    return wf
