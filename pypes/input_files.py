"""
Workflows to grab input file structures.
"""
import os
import os.path as op

import nipype.pipeline.engine as pe
from   nipype.interfaces.utility import IdentityInterface
from   nipype.interfaces.io import SelectFiles

from ._utils import _check_list, remove_ext


def subject_session_input(base_dir, session_names, file_names, subject_ids=None,
                          wf_name="subject_session_files"):
    """ A workflow of IdentityInterface->SelectFiles for the case where
    you have a {subject_id}/{session_id}/{image_file} dataset structure.

    Parameters
    ----------
    base_dir: str
        Path to the working directory of the workflow

    session_names: list of str
        Example: ['session_0']

    file_names: list of str
        Example: ['mprage.nii.gz', 'rest.nii.gz']
        Example: ['anat_1/mprage.nii.gz', 'rest_1/rest.nii.gz']

    subject_ids: list of str
        Use this if you want to limit the analysis to certain subject IDs.
        If `None` will pick the folders from os.listdir(data_dir).

    wf_name: str
        Name of the workflow

    Returns
    -------
    wf: nipype Workflow

    Notes
    -----
    - 'select.{file_name_without_extension}' will give you the path of the {file_name}s.
    - 'infosrc.subject_id' will give you the 'subject_id's.
    """
    # Check the subject ids
    subj_ids = _check_list(subject_ids)
    if subj_ids is None:
        subj_ids = [op.basename(p) for p in os.listdir(base_dir)]

    # the fields and its values for the fields_iterables
    fields = [('session_id', session_names),
              ('subject_id', subj_ids),]

    files = {'{}'.format(remove_ext(op.basename(f))): '{subject_id}/{session_id}/' +
                                        '{}'.format(f) for f in file_names}

    return input_file_wf(work_dir=base_dir,
                         data_dir=base_dir,
                         field_iterables=fields,
                         file_templates=files,
                         wf_name=wf_name)


def input_file_wf(work_dir, data_dir, field_iterables, file_templates, wf_name="input_files"):
    """ A workflow of IdentityInterface->SelectFiles for the case where
    you have a {subject_id}/{session_id}/{image_file} dataset structure.

    Parameters
    ----------
    work_dir: str
        Path to the working directory of the workflow

    data_dir: str

    field_iterables: List of 2-tuples (str, iterable)
        Example: [('session_id', session_names),
                  ('subject_id', subject_ids),]
        This will be input to an IdentityInterface

    file_templates: Dict[str -> str]
        Example: {'anat_hc': '{subject_id}/{session_id}/anat_hc.nii.gz',
                  'pet_fdg': '{subject_id}/{session_id}/pet_fdg.nii.gz',
                 }

    wf_name: str
        Name of the workflow

    Returns
    -------
    wf: nipype Workflow
    """
    # Input workflow
    wf = pe.Workflow(name=wf_name, base_dir=work_dir)

    # Infosource - a function free node to iterate over the list of subject names
    field_names = [field[0] for field in field_iterables]

    infosource = pe.Node(IdentityInterface(fields=field_names), name="infosrc")
    infosource.iterables = field_iterables

    # SelectFiles
    select = pe.Node(SelectFiles(file_templates, base_directory=data_dir), name="select")

    # Connect, e.g., 'infosrc.subject_id' to 'select.subject_id'
    wf.connect([(infosource, select, [(field, field) for field in field_names])])

    return wf

