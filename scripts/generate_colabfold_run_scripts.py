#!/usr/bin/env python3

import argparse
import functools
import logging
import os
import pathlib
import shlex
import sys
from typing import List, Optional, Tuple, Union


def _existing_file(arg: str) -> pathlib.Path:
    if (path := pathlib.Path(arg)).is_file():
        return path

    raise argparse.ArgumentTypeError(f'Not an existing file: "{arg}"')


def _existing_folder(arg: str) -> pathlib.Path:
    if (path := pathlib.Path(arg)).is_dir():
        return path

    raise argparse.ArgumentTypeError(f'Not an existing folder: "{arg}"')


def _positive_int(arg) -> float:
    if (n := int(arg)) > 0:
        return n

    raise argparse.ArgumentTypeError("Not a positive int")


def _directory_is_empty(directory: Union[pathlib.Path, str]) -> bool:
    return not any(pathlib.Path(directory).iterdir())


def _make_cli() -> argparse.ArgumentParser:

    cli = argparse.ArgumentParser()

    cli.add_argument(
        "apptainer-img",
        type=_existing_file,
        help="Path to the colabfold's Apptainer image.",
    )
    cli.add_argument(
        "query-file",
        type=_existing_file,
        help="Path to a FASTA file with the proteins to be modeled.",
    )
    cli.add_argument(
        "cache-folder",
        type=_existing_folder,
        help="Path to colabfold's cache folder.",
    )
    cli.add_argument(
        "output-folder",
        type=pathlib.Path,
        help="Path to a folder where to store output files.",
    )
    cli.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing file(s).",
    )

    cli.add_argument(
        "--ncpus",
        type=_positive_int,
        required=True,
        help="Maximum number of CPUs to use.",
    )

    cli.add_argument(
        "--job-name",
        type=str,
        help="A human-friendly job name.",
    )

    return cli


@functools.cache
def _get_account_code() -> str:
    code = os.getenv("SLURM_PROJECT_ID")
    if code is None:
        raise RuntimeError(
            "Please define environment variable 'SLURM_PROJECT_ID' with the account code to be used when submitting jobs to SLURM."
        )

    return shlex.quote(code)


def _generate_colabfold_search_args(
    img: pathlib.Path,
    cache_dir: pathlib.Path,
    query_file: pathlib.Path,
    output_folder: pathlib.Path,
    ncpus: int,
) -> Tuple[List[str], pathlib.Path]:
    cache_dir_src = cache_dir.resolve()
    cache_dir_dest = pathlib.Path("/tmp/cache")
    query_file_src = query_file.resolve()
    query_file_dest = pathlib.Path("/input") / query_file_src.name
    output_folder_src = output_folder.resolve()
    output_folder_dest = pathlib.Path("/output")

    colabfold_search_output_folder = output_folder_dest / "search"

    args = [
        "apptainer",
        "run",
        f"--bind={cache_dir_src}:{cache_dir_dest}",
        f"--bind={query_file_src}:{query_file_dest}:ro",
        f"--bind={output_folder_src}:{output_folder_dest}",
        str(img),
        "--env=MMSEQS_IGNORE_INDEX=1",
        "colabfold_search",
        f"--threads={ncpus}",
        str(query_file_dest),
        str(cache_dir_dest),
        str(colabfold_search_output_folder),
    ]

    return args, colabfold_search_output_folder


def _generate_colabfold_batch_args(
    img: pathlib.Path,
    cache_dir: pathlib.Path,
    input_folder: pathlib.Path,
    output_folder: pathlib.Path,
) -> Tuple[List[str], pathlib.Path]:
    cache_dir_src = cache_dir.resolve()
    cache_dir_dest = pathlib.Path("/tmp/cache")
    input_folder_src = input_folder.resolve()
    input_folder_dest = pathlib.Path("/input")
    output_folder_src = output_folder.resolve()
    output_folder_dest = pathlib.Path("/output")

    colabfold_predict_output_folder = output_folder_dest / "predict"

    args = [
        "apptainer",
        "run",
        f"--bind={cache_dir_src}:{cache_dir_dest}",
        f"--bind={input_folder_src}:{input_folder_dest}",
        f"--bind={output_folder_src}:{output_folder_dest}",
        str(img),
        "colabfold_batch",
        str(input_folder_dest),
        str(colabfold_predict_output_folder),
    ]

    return args, colabfold_predict_output_folder


def _generate_sbatch_script(
    args: List[str],
    num_cpus: int,
    memory_gbs: float,
    max_time: str,
    partition: str,
    job_name: Optional[str] = None,
    num_gpus: int = 0,
) -> str:
    if job_name is None:
        job_name = "colabfold_search"
    else:
        job_name = shlex.quote(f"{job_name}_colabfold_search")

    mem_per_cpu = max(1.0, round(memory_gbs / num_cpus, 2))

    if num_gpus > 0:
        partition = "accel"

    assert args[0] == "apptainer"
    assert args[1] == "run"

    prefix = shlex.join(args[:2])
    args = args[2:].copy()
    for i, tok in enumerate(args):
        args[i] = shlex.quote(tok)

    args.insert(0, prefix)

    lines = [
        "#!/usr/bin/env bash",
        "set -e",
        "set -u",
        "set -o pipefail",
        "",
    ]

    sbatch_directives = [
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --account={_get_account_code()}",
        f"#SBATCH --time={shlex.quote(max_time)}",
        "#SBATCH --ntasks=1",
        f"#SBATCH --mem-per-cpu={mem_per_cpu:.2g}GB",
        f"#SBATCH --cpus-per-task={num_cpus}",
    ]

    if num_gpus > 0:
        sbatch_directives.append(f"#SBATCH --gpus={num_gpus}")

    if partition is not None:
        sbatch_directives.append(f"#SBATCH --partition={shlex.quote(partition)}"),

    lines.extend(sorted(sbatch_directives))

    lines.extend(
        (
            "",
            " \\\n    ".join(args),
        )
    )

    return "\n".join(lines)


def setup_logger(level: str):
    fmt = "[%(asctime)s] %(levelname)s: %(message)s"
    logging.basicConfig(level=level, format=fmt)
    logging.getLogger().setLevel(level)


def main() -> int:
    setup_logger("INFO")

    args = vars(_make_cli().parse_args())

    colabfold_search_args, colabfold_search_output_folder = _generate_colabfold_search_args(
        img=args["apptainer-img"],
        cache_dir=args["cache-folder"],
        query_file=args["query-file"],
        output_folder=args["output-folder"],
        ncpus=args["ncpus"],
    )

    colabfold_batch_args, colabfold_batch_output_folder = _generate_colabfold_batch_args(
        img=args["apptainer-img"],
        cache_dir=args["cache-folder"],
        input_folder=colabfold_search_output_folder,
        output_folder=args["output-folder"],
    )

    if not args["force"] and args["output-folder"].exists() and not _directory_is_empty(args["output-folder"]):
        raise RuntimeError(f"Refusing to non-empty folder \"{args['output-folder']}\". Pass --force to overwrite.")

    colabfold_search_script = args["output-folder"] / "run_colabfold_search.sh"
    colabfold_batch_script = args["output-folder"] / "run_colabfold_batch.sh"
    if args["force"]:
        colabfold_search_script.unlink(missing_ok=True)
        colabfold_batch_script.unlink(missing_ok=True)

    logging.info('writing colabfold_search runner to file "%s"...', colabfold_search_script)
    with colabfold_search_script.open("w") as f:
        f.write(
            _generate_sbatch_script(
                args=colabfold_search_args,
                num_cpus=args["ncpus"],
                memory_gbs=10,
                max_time="08:00:00",
                partition="normal",
                job_name=args["job_name"],
            )
        )

    logging.info('writing colabfold_batch runner to file "%s"...', colabfold_batch_script)
    with colabfold_batch_script.open("w") as f:
        f.write(
            _generate_sbatch_script(
                args=colabfold_batch_args,
                num_cpus=1,
                memory_gbs=8,
                max_time="04:00:00",
                partition="normal",
                job_name=args["job_name"],
                num_gpus=1,
            )
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
