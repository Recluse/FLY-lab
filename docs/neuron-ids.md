# Neuron identifiers used

All identifiers below come from the pinned [official FlyWire annotations](https://github.com/flyconnectome/flywire_annotations/blob/8587524c1748ce5ef2080822a2fc890fc03bf597/supplemental_files/Supplemental_file1_neuron_annotations.tsv), materialisation 783, and were checked against `Completeness_783.csv`. For sensory cells, *side* means the side at which the nerve enters, which is not the same convention as the sides in the original notebook.

## Inputs used by variants C, D and E

Mechanosensory head bristles, selected by `cell_class = mechanosensory` and `cell_sub_class = head bristle`: **150 cells on the left, 155 on the right**, all present in the model. The complete list of identifiers used by any given run is stored in that run's `wiring.json`, so it is reproduced from the data rather than copied here.

## Descending readout

Every annotated neuron with `super_class = descending` and side left or right: **645 on the left, 646 on the right**. Four further annotated descending neurons are absent from the model's completeness table and are recorded as excluded in each run's `wiring.json`.

## Verified steering-neuron identifiers

Confirmed against the [primary publication](https://elifesciences.org/articles/102230) and the `cell_type` field of the annotations. `cell_type` takes precedence over `hemibrain_type`: other cells carry the historical hemibrain label DNa01, and matching on that string would pick the wrong neurons.

| Type | FlyWire ID (783) | Role in this work |
|---|---|---|
| DNa01L | 720575940627787609 | secondary measurement only |
| DNa01R | 720575940644438551 | secondary measurement only |
| DNa02L | 720575940629327659 | secondary measurement only |
| DNa02R | 720575940604737708 | secondary measurement only |

These four neurons are recorded per tick but take no part in the command, because single cells fire too rarely to be read within a 15 ms tick.

## MN9

`720575940660219265`, taken from cell 17 of the authors' `example.ipynb`, materialisation 630. Used only to confirm that the brain model responds to sugar as published. **MN9 is not a validated stop or turn output**, and feeding is not implemented anywhere in this work.

## Version discrepancies found in the sugar sets

The sugar-responsive sets of the original notebook (materialisation 630) do not map cleanly onto the 783 annotations. Two identifiers are absent from 783 altogether, and the side labels are opposite: cells listed as the right-hand set in the notebook are annotated as entering on the left, and vice versa. We did not carry either convention over silently; the diagnostic runs on 783 define their input from the annotations directly.

| Notebook set (630) | FlyWire ID | Annotation in 783 | Nerve-entry side in 783 |
|---|---|---|---|
| sugarR (example.ipynb) | 720575940624963786 | sugar/water | left |
| sugarR (example.ipynb) | 720575940630233916 | sugar/water | left |
| sugarR (example.ipynb) | 720575940637568838 | sugar/water | left |
| sugarR (example.ipynb) | 720575940638202345 | sugar/water | left |
| sugarR (example.ipynb) | 720575940617000768 | sugar/water | left |
| sugarR (example.ipynb) | 720575940630797113 | sugar/water | left |
| sugarR (example.ipynb) | 720575940632889389 | sugar/water | left |
| sugarR (example.ipynb) | 720575940621754367 | sugar/water | left |
| sugarR (example.ipynb) | 720575940621502051 | sugar/water | left |
| sugarR (example.ipynb) | 720575940640649691 | sugar/water | left |
| sugarR (example.ipynb) | 720575940639332736 | sugar/water | left |
| sugarR (example.ipynb) | 720575940616885538 | sugar/water | left |
| sugarR (example.ipynb) | 720575940639198653 | sugar/water | left |
| sugarR (example.ipynb) | 720575940620900446 | not found | — |
| sugarR (example.ipynb) | 720575940617937543 | sugar/water | left |
| sugarR (example.ipynb) | 720575940632425919 | sugar/water | left |
| sugarR (example.ipynb) | 720575940633143833 | sugar/water | left |
| sugarR (example.ipynb) | 720575940612670570 | sugar/water | left |
| sugarR (example.ipynb) | 720575940628853239 | sugar/water | left |
| sugarR (example.ipynb) | 720575940629176663 | sugar/water | left |
| sugarR (example.ipynb) | 720575940611875570 | sugar/water | left |
| sugarL (figures.ipynb) | 720575940620589838 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940631147148 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940608305161 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940629388135 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940630968335 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940606801282 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940617398502 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940616167218 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940620296641 | sugar/water | right |
| sugarL (figures.ipynb) | 720575940627961104 | not found | — |

## Full diagnostic input list

The 129 gustatory sugar/water cells of materialisation 783 used in the earlier diagnostic runs, 67 on the left and 62 on the right, are listed in [`neuron-ids-sugar-783.md`](neuron-ids-sugar-783.md). Every run also stores its own `sensory_ids.json` containing the annotation rows verbatim, together with the annotation commit and the file's SHA-256.
