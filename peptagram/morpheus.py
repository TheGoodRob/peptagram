 # -*- coding: utf-8 -*-
from __future__ import print_function
from pprint import pprint
import os
import json
import csv
import logging
import math

import parse
import proteins as parse_proteins
import peptidemass

"""
Parser for Morpheus files
"""


logger = logging.getLogger('morpheus')


def read_modification_dict(modifications_tsv):
  result = {}
  for entry in parse.read_tsv(modifications_tsv):
    # pprint(entry)
    key = entry['description']
    mass = float(entry['monoisotopic mass shift (da)'])
    if 'residue' in entry:
      aa = entry['residue']
    elif 'amino acid residue' in entry:
      aa = entry['amino acid residue']
    else:
      aa = 'n/a'
    if aa != 'n/a':
      mass += peptidemass.aa_monoisotopic_mass[aa]
    result[key] = mass
  return result


def parse_peptide(text, modification_dict):
  seq = text.split('.')[1]
  chars = []
  modifications = []
  in_modification = False
  mod_str = ''
  for c in seq:
    if in_modification:
      if c == ']':
        in_modification = False
        i = len(chars) - 1
        if mod_str not in modification_dict:
          print('Warning: modification {} unknown'.format(mod_str))
          continue
        modification = {
            'i':i, 
            'mass': modification_dict[mod_str],
        }
        modifications.append(modification)
      else:
        mod_str += c
    else:
      if c == '[':
        in_modification = True
        mod_str = ''
      else:
        chars.append(c)
  return ''.join(chars), modifications


def get_first(s, delimiter='/'):
  if not isinstance(s, str):
    return s
  elif delimiter not in s:
    return s
  return s.split(delimiter)[0].strip()


def get_proteins(protein_groups_fname, psm_fname, modifications_fname=None):
  dump_dir = os.path.dirname(protein_groups_fname)
  if modifications_fname is not None:
    modification_table = read_modification_dict(modifications_fname)
  else:
    modification_table = {}
  peptides = parse.read_tsv(psm_fname)
  protein_groups = parse.read_tsv(protein_groups_fname)

  if logger.root.level <= logging.DEBUG:
    dump = os.path.join(dump_dir, 'peptides.dump')
    logger.debug('Dumping peptides data structure to ' + dump)
    parse.save_data_dict(peptides, dump)
    dump = os.path.join(dump_dir, 'protein_groups.dump')
    logger.debug('Dumping protein_groups data structure to ' + dump)
    parse.save_data_dict(protein_groups, dump)

  proteins = {}
  for i_group, protein_group in enumerate(protein_groups):
    descriptions = protein_group['protein description'].split(' / ')
    coverage =  float(get_first(protein_group['protein sequence coverage (%)'], ';'))
    seqs = protein_group['protein sequence'].split('/')
    seqids = [desc.split()[0] for desc in descriptions]
    for seqid in seqids:
      if seqid in proteins:
        logger.warning("Different protein groups claim same first seqid", seqid)
    protein = {
      'description': descriptions[0],
      'sequence': seqs[0],
      'other_sequences': seqs[1:],
      'attr': {
        'coverage': parse.round_decimal(coverage, 4),
        'morpheus-score': parse.round_decimal(protein_group['summed morpheus score'], 4),
        'i_group': i_group,
        'other_seqids': seqids[1:],
        'seqid': seqids[0],
      },
      'sources': [{ 'peptides':[] }]
    }
    proteins[seqids[0]] = protein

  protein_by_seqid = {}
  for seqid in proteins:
    protein = proteins[seqid]
    protein_by_seqid[seqid] = protein
    for alt_seqid in protein['attr']['other_seqids']:
      protein_by_seqid[alt_seqid] = protein
  unmatched_peptides = []
  n_peptide_matched = 0
  for src_peptide in peptides:
    descriptions = src_peptide['protein description'].split(' / ')
    peptide_seqids = [d.split()[0] for d in descriptions]
    protein = None
    for peptide_seqid in peptide_seqids:
      if peptide_seqid in protein_by_seqid:
        protein = protein_by_seqid[peptide_seqid]
        # if peptide_seqid != protein['attr']['seqid']:
        #   print('secondary seqid', protein['attr']['seqid'], peptide_seqid)
        break
    if protein is None:
      unmatched_peptides.append(src_peptide)
      continue
    n_peptide_matched += 1
    sequence = protein['sequence']
    peptide_sequence, modifications = parse_peptide(
        src_peptide['peptide sequence'],
        modification_table)
    peptide_sequence = src_peptide['base peptide sequence']
    i = sequence.find(peptide_sequence)
    if i < 0:
      print('Warning:', peptide_sequence, 'not found in', protein['attr']['seqid'])
      continue
    q_value = float(src_peptide['q-value (%)'])
    if 'scan number' in src_peptide:
      scan_id = src_peptide['scan number']
    elif 'spectrum index' in src_peptide:
      scan_id = src_peptide['spectrum index']
    else:
      scan_id = ''
    if 'retention time (min)' in src_peptide:
      time = parse.round_decimal(src_peptide['retention time (min)'], 4)
    elif 'retention time (minutes)' in src_peptide:
      time = parse.round_decimal(src_peptide['retention time (minutes)'], 4)
    else:
      time = ''

    peptide = {
      'sequence': peptide_sequence,
      'attr': {
        'scan_id': scan_id, 
        'retention_time': time,
        'morpheus_score': parse.round_decimal(src_peptide['morpheus score'], 4),
        'mass': parse.round_decimal(src_peptide['precursor mass (da)'], 4),
        'mass_diff': parse.round_decimal(src_peptide['precursor mass error (da)'], 4),
        'm/z': parse.round_decimal(src_peptide['precursor m/z'], 4),
        'source': parse.basename(src_peptide['filename']),
        'q_value': q_value,
      },
      'intensity': 1.0 - q_value/100.0,
      'i': i,
    }
    if modifications:
      for modification in modifications:
        modification['mass'] = parse.round_decimal(modification['mass'], 4)
      peptide['attr']['modifications'] = modifications

    protein['sources'][0]['peptides'].append(peptide)

  dump = os.path.join(dump_dir, 'proteins.dump')
  logger.debug('Dumping proteins data structure to ' + dump)
  if logger.root.level <= logging.DEBUG:
    parse.save_data_dict(proteins, dump)

  logger.info("Assigned {}/{} of PSMs.tsv to protein_groups.tsv".format(n_peptide_matched, len(unmatched_peptides)))

  return proteins


if __name__ == '__main__':
  logging.basicConfig(level=logging.DEBUG)
  proteins = get_proteins(
      '../example/morpheus/OK20130822_MPProtomap_KO1.protein_groups.tsv',
      '../example/morpheus/OK20130822_MPProtomap_KO1.PSMs.tsv',
      '../example/morpheus/modifications.tsv')


