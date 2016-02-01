# -*- coding: utf-8 -*-
"""
Nipype workflows to process diffusion MRI.
"""
import os.path as op

import nipype.interfaces.spm     as spm
import nipype.pipeline.engine    as pe
from   nipype.interfaces.fsl     import ExtractROI, Eddy, DTIFit, MultiImageMaths
from   nipype.interfaces.io      import DataSink, SelectFiles
from   nipype.interfaces.utility import Function, Select, Split
from   nipype.algorithms.misc    import Gunzip

from   .anat        import attach_spm_anat_preprocessing
from   .preproc     import spm_coregister
from   .utils       import find_wf_node
from   ._utils      import flatten_list

def write_acquisition_parameters(in_file):
    """
    # Comments on the `eddy` tool from FSL FDT.

    A description of the tool:
    http://fsl.fmrib.ox.ac.uk/fsl/fslwiki/Eddy/UsersGuide

    Our problem to run this tool instead of the good-old `eddy_correct` is the `--acqp` argument, an
    acquisitions parameters file.

    A detailed description of the --acpq input file is here:
    http://fsl.fmrib.ox.ac.uk/fsl/fslwiki/eddy/Faq#How_do_I_know_what_to_put_into_my_--acqp_file

    In the following subsections I describe each of the fields needed to check and build the acquisitions parameters file.

    ## Phase Encoding Direction
    Dicom header field: (0018,1312) InPlanePhaseEncodingDirection
    The phase encoding direction is the OPPOSITE of frequency encoding direction:
    - 'COL' = A/P (freqDir L/R),
    - 'ROW' = L/R (freqDir A/P)


    Nifti header field: "descrip.phaseDir:'+'" is for 'COL' in the DICOM InPlanePhaseEncodingDirection value.
    So if you have only one phase encoding oriendation and a '+' in the previous header field,
    the first 3 columns for the `--acqp` parameter file should be:
    0 1 0

    indicating that the scan was acquired with phase-encoding in the anterior-posterior direction.

    For more info:
    http://web.stanford.edu/group/vista/cgi-bin/wiki/index.php/DTI_Preprocessing_User_Manual#Frequency_vs_Phase_Encode_Direction
    https://xwiki.nbirn.org:8443/xwiki/bin/view/Function-BIRN/PhaseEncodeDirectionIssues


    ## Effective Echo Spacing (aka dwell time)

    Effective Echo Spacing (s) = 1/(BandwidthPerPixelPhaseEncode * MatrixSizePhase)

    effective echo spacing = 1 / [(0019,1028) * (0051,100b component #1)] (from the archives)
    https://www.jiscmail.ac.uk/cgi-bin/webadmin?A3=ind1303&L=FSL&E=quoted-printable&P=29358&B=--B_3444933351_15386849&T=text%2Fhtml;%20charset=ISO-8859-1&pending=

    The dwell time is in the nifti header `descrip.dwell`, in seconds (or look at the field `time_units`).
    http://www.mit.edu/~satra/nipype-nightly/interfaces/generated/nipype.interfaces.fsl.epi.html

    More info:
    http://lcni.uoregon.edu/kb-articles/kb-0003

    ## EPI factor

    The EPI factor is not included in the nifti header.
    You can read it using the Grassroots DICOM tool called `gdcmdump`, for example:
    >>> gdcmdump -C IM-0126-0001.dcm | grep 'EPIFactor'
    sFastImaging.lEPIFactor                  = 128

    More info:
    http://dicomlookup.com/default.htm


    # The fourth element of the acquisitions parameter file

    The fourth element in each row is the time (in seconds) between reading the center of the first echo and reading the
    center of the last echo.
    It is the "dwell time" multiplied by "number of PE steps - 1" and it is also the reciprocal of the PE bandwidth/pixel.

    Total readout time (FSL) = (number of echoes - 1) * echo spacing

    Total Readout Time (SPM) = 1/(BandwidthPerPixelPhaseEncode)
    Since the Bandwidth Per Pixel Phase Encode is in Hz, this will give the readout time in seconds


    # The `---index` argument

    The index argument is a text file with a row of numbers. Each number
    indicates what line (starting from 1) in the `acqp` file corresponds to
    each volume in the DTI acquisition.

    # What to do now with the `dcm2nii` files?

    I see two options to calculate the `acqp` lines with these files.

    1. We already have the `dwell` but we don't have the EPI factor.
    We know that the standard in Siemens is 128 and we could stick to that.

    2. Use the `slice_duration * 0.001` which is very near the calculated value.

    # Summary

    So, for example, if we had these acquisition parameters:

    ```
    Phase enc. dir. P >> A
    Echo spacing 0.75 [ms]
    EPI factor 128
    ```

    We should put in the `acqp` file this line:
    0 1 0 0.095

    """

    import nibabel
    import os.path

    acqp_file = "diff.acqp"
    index_file = "diff.index"

    image = nibabel.load(in_file)
    n_directions = image.shape[-1]
    header = image.header
    descrip = dict([item.split("=", 1) for item in header["descrip"][()].split(";")])

    if descrip.get("phaseDir") == "+":
        pe_axis = "0 1 0"
    elif descrip.get("phaseDir") == "-":
        pe_axis = "0 -1 0"
    else:
        raise ValueError("unexpected value for phaseDir: {}".format(descrip.get("phaseDir")))

    # Siemens standard
    epi_factor = 128
    # (number of phase-encode steps - 1) * (echo spacing time in milliseconds) * (seconds per millisecond)
    total_readout_time = (epi_factor - 1) * float(descrip["dwell"]) * 1e-3

    with open(acqp_file, "wt") as fout:
        fout.write("{} {}\n".format(pe_axis, total_readout_time))
    with open(index_file, "wt") as fout:
        fout.write("{}\n".format(" ".join(n_directions * ["1"])))

    return os.path.abspath(acqp_file), os.path.abspath(index_file)

def fsl_dti_preprocessing(wf_name="fsl_dti_preproc"):
    """ Run the diffusion MRI pre-processing workflow against the diff files in `data_dir`.

    It does:
    - Eddy
    - DTIFit

    Nipype Inputs
    -------------
    eddy.in_file: traits.File
        path to the diffusion MRI image
    extract_b0.in_file: traits.File
        path to the diffusion MRI image
    coreg_b0.source: traits.File
        path to the anatomical image for co-registration
    dtifit.bvecs: traits.File
        path to the b vectors file
    dtifit.bvals: traits.File
        path to the b values file

    Returns
    -------
    wf: nipype Workflow
    """

    write_acqp     = pe.Node(Function(
        input_names=["in_file"],
        output_names=["out_acqp", "out_index"],
        function=write_acquisition_parameters),                 name="write_acqp")
    extract_b0   = pe.Node(ExtractROI(t_min=0, t_size=1),       name="extract_b0")
    gunzip_b0    = pe.Node(Gunzip(),                            name="gunzip_b0")
    coreg_b0     = pe.Node(spm_coregister(cost_function="mi"),  name="coreg_b0")
    brain_sel    = pe.Node(Select(index=[0, 1, 2]),             name="brain_sel")
    brain_split  = pe.Node(Split(splits=[1, 2], squeeze=True),  name="brain_split")
    brain_merge  = pe.Node(MultiImageMaths(),                   name="brain_merge")
    eddy         = pe.Node(Eddy(),                              name="eddy")
    dtifit       = pe.Node(DTIFit(save_tensor=True),            name="dtifit")

    brain_merge.inputs.op_string = "-add '%s' -add '%s' -abs -bin"
    brain_merge.inputs.out_file = "brain_mask.nii.gz"

    # Create the workflow object
    wf = pe.Workflow(name=wf_name)

    # Connect the nodes
    wf.connect([
                (write_acqp,    eddy,           [("out_acqp",               "in_acqp"),
                                                 ("out_index",              "in_index")]),
                (extract_b0,    gunzip_b0,      [("roi_file",               "in_file")]),
                (gunzip_b0,     coreg_b0,       [("out_file",               "target")]),
                (brain_sel,     coreg_b0,       [(("out", flatten_list),    "apply_to_files")]),
                (coreg_b0,      brain_split,    [("coregistered_files",     "inlist")]),
                (brain_split,   brain_merge,    [("out1",                   "in_file")]),
                (brain_split,   brain_merge,    [("out2",                   "operand_files")]),
                (brain_merge,   eddy,           [("out_file",               "in_mask")]),
                (eddy,          dtifit,         [("out_corrected",          "dwi")]),
                (brain_merge,   dtifit,         [("out_file",               "mask")]),
              ])
    return wf


def attach_fsl_dti_preprocessing(main_wf, wf_name="fsl_dti_preproc"):
    """ Attach the FSL-based diffusion MRI pre-processing workflow to the `main_wf`.

    Parameters
    ----------
    main_wf: nipype Workflow

    wf_name: str
        Name of the preprocessing workflow

    Nipype Inputs for `main_wf`
    ---------------------------
    Note: The `main_wf` workflow is expected to have an `input_files` and a `datasink` nodes.

    input_files.select.diff: input node

    datasink: nipype Node

    Returns
    -------
    main_wf: nipype Workflow
    """
    main_wf = attach_spm_anat_preprocessing(main_wf=main_wf,
                                            wf_name="spm_anat_preproc")

    in_files = find_wf_node(main_wf, SelectFiles)
    datasink = find_wf_node(main_wf, DataSink)
    anat_wf  = main_wf.get_node("spm_anat_preproc")

    # The workflow box
    dti_wf = fsl_dti_preprocessing(wf_name=wf_name)

    # input and output diffusion MRI workflow to main workflow connections
    main_wf.connect([(in_files, dti_wf,   [("diff",                                  "eddy.in_file"),
                                           ("diff",                                  "write_acqp.in_file"),
                                           ("diff",                                  "extract_b0.in_file"),
                                           ("diff_bval",                             "dtifit.bvals"),
                                           ("diff_bvec",                             "dtifit.bvecs"),
                                           ("diff_bval",                             "eddy.in_bval"),
                                           ("diff_bvec",                             "eddy.in_bvec")]),
                     (anat_wf,  dti_wf,   [("new_segment.native_class_images",       "brain_sel.inlist"),
                                           ("gunzip_anat.out_file",                  "coreg_b0.source")]),
                     (dti_wf,   datasink, [("eddy.out_corrected",                    "diff.@eddy_corrected"),
                                           ("dtifit.V1",                             "diff.@v1"),
                                           ("dtifit.V2",                             "diff.@v2"),
                                           ("dtifit.V3",                             "diff.@v3"),
                                           ("dtifit.L1",                             "diff.@l1"),
                                           ("dtifit.L2",                             "diff.@l2"),
                                           ("dtifit.L3",                             "diff.@l3"),
                                           ("dtifit.MD",                             "diff.@mean_diffusivity"),
                                           ("dtifit.FA",                             "diff.@fractional_anisotropy"),
                                           ("dtifit.MO",                             "diff.@mode_of_anisotropy"),
                                           ("dtifit.S0",                             "diff.@s0"),
                                           ("dtifit.tensor",                         "diff.@tensor"),],),
                    ])

    return main_wf