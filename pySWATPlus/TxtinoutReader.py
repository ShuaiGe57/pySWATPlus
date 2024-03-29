import subprocess
import os
from pySWATPlus.FileReader import FileReader
import shutil
import tempfile
import multiprocessing
import tqdm
from pathlib import Path
import datetime
from typing import List, Dict, Tuple, Optional
import dask.distributed
import re


class TxtinoutReader:

    def __init__(self, path: str) -> None:

        """
        Initialize a TxtinoutReader instance for working with SWAT model data.

        Parameters:
        path (str or Path): The path to the SWAT model folder.

        Raises:
        TypeError: If the provided path is not a string or a Path object, or if the folder does not exist,
                    or if there is more than one .exe file in the folder, or if no .exe file is found.

        Attributes:
        root_folder (Path): The path to the root folder of the SWAT model.
        swat_exe_path (Path): The path to the main SWAT executable file.
        """

        # check if path is a string or a path
        if isinstance(path, str):
            # convert to path
            path = Path(path)
        elif not isinstance(path, Path):
            raise TypeError("path must be a string or a Path object")

        # check if folder exists
        if not os.path.isdir(path):
            raise FileNotFoundError("folder does not exist")

        # count files that end with .exe
        count = 0
        swat_exe = None
        for file in os.listdir(path):
            if file.endswith(".exe"):
                if count == 0:
                    swat_exe = file
                elif count > 0:
                    raise TypeError("More than one .exe file found in the parent folder")
                count += 1

        if count == 0:
            raise TypeError(".exe not found in parent folder")

        # find parent directory
        self.root_folder = path
        self.swat_exe_path = path / swat_exe

    def _build_line_to_add(self, obj: str, daily: bool, monthly: bool, yearly: bool, avann: bool) -> str:
        """
        Build a line to add to the 'print.prt' file based on the provided parameters.

        Parameters:
        obj (str): The object name or identifier.
        daily (bool): Flag for daily print frequency.
        monthly (bool): Flag for monthly print frequency.
        yearly (bool): Flag for yearly print frequency.
        avann (bool): Flag for average annual print frequency.

        Returns:
        str: A formatted string representing the line to add to the 'print.prt' file.
        """
        print_periodicity = {
            'daily': daily,
            'monthly': monthly,
            'yearly': yearly,
            'avann': avann,
        }

        arg_to_add = obj.ljust(29)
        for value in print_periodicity.values():
            if value:
                periodicity = 'y'
            else:
                periodicity = 'n'

            arg_to_add += periodicity.ljust(14)

        arg_to_add = arg_to_add.rstrip()
        arg_to_add += '\n'
        return arg_to_add

    def enable_object_in_print_prt(self, obj: str, daily: bool, monthly: bool, yearly: bool, avann: bool) -> None:
        """
        Enable or update an object in the 'print.prt' file. If obj is not a default identifier, it will be added at the end of the file.

        Parameters:
        obj (str): The object name or identifier.
        daily (bool): Flag for daily print frequency.
        monthly (bool): Flag for monthly print frequency.
        yearly (bool): Flag for yearly print frequency.
        avann (bool): Flag for average annual print frequency.

        Returns:
        None
        """

        # check if obj is object itself or file
        if os.path.splitext(obj)[1] != '':
            arg_to_add = obj.rsplit('_', maxsplit=1)[0]
        else:
            arg_to_add = obj

        # read all print_prt file, line by line
        print_prt_path = self.root_folder / 'print.prt'
        new_print_prt = ""
        found = False
        with open(print_prt_path) as file:
            for line in file:
                if not line.startswith(
                        arg_to_add + ' '):  # Line must start exactly with arg_to_add, not a word that starts with arg_to_add
                    new_print_prt += line
                else:
                    # obj already exist, replace it in same position
                    new_print_prt += self._build_line_to_add(arg_to_add, daily, monthly, yearly, avann)
                    found = True

        if not found:
            new_print_prt += self._build_line_to_add(arg_to_add, daily, monthly, yearly, avann)

        # store new print_prt
        with open(print_prt_path, 'w') as file:
            file.write(new_print_prt)

    # modify yrc_start and yrc_end
    def set_simulation_time(self, start_date: str, end_date: str, step: int = 0) -> None:
        """
        Modify the beginning and end time in the 'time.sim' file.

        Parameters:
        day_start (int): The new beginning day of the year.
        year_start (int): The new beginning year.
        day_end (int): The new end day of the year.
        year_end (int): The new end year.
        step (int): The new modelling step, default 0.

        Returns:
        None
        """

        nth_line = 3

        # time_sim_path = f"{self.root_folder}\\{'time.sim'}"
        time_sim_path = self.root_folder / 'time.sim'

        start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
        day_start = start.timetuple().tm_yday
        year_start = start.timetuple().tm_year
        day_end = end.timetuple().tm_yday
        year_end = end.timetuple().tm_year

        # Open the file in read mode and read its contents
        with open(time_sim_path, 'r') as file:
            lines = file.readlines()

        year_line = lines[nth_line - 1]

        # Split the input string by spaces
        elements = year_line.split()

        elements[0] = day_start
        elements[1] = year_start
        elements[2] = day_end
        elements[3] = year_end
        elements[4] = step

        # Reconstruct the result string while maintaining spaces
        result_string = '{: >8} {: >10} {: >10} {: >10} {: >10} \n'.format(*elements)

        lines[nth_line - 1] = result_string

        with open(time_sim_path, 'w') as file:
            file.writelines(lines)

    # modify warmup
    def set_print_time(self, start_date: str = None, end_date: str = None, warmup: int = 0, interval: int = 1) -> None:
        """
        Modify the warmup period in the 'print.prt' file.

        Parameters:
        warmup (int): The new warmup period value.
        start_date (str): The new start date
        end_date (str): The new end date
        interval (int): The new print interval

        Returns:
        None
        """
        time_sim_path = self.root_folder / 'print.prt'

        # Open the file in read mode and read its contents
        with open(time_sim_path, 'r') as file:
            lines = file.readlines()

        nth_line = 3
        year_line = lines[nth_line - 1]

        # Split the input string by spaces
        elements = year_line.split()

        elements[0] = warmup
        elements[5] = interval
        # Use nyskip or specific time
        if start_date and end_date:
            # Calculate nday and year
            start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.datetime.strptime(end_date, "%Y-%m-%d")
            day_start = start.timetuple().tm_yday
            year_start = start.timetuple().tm_year
            day_end = end.timetuple().tm_yday
            year_end = end.timetuple().tm_year
            elements[1] = day_start
            elements[2] = year_start
            elements[3] = day_end
            elements[4] = year_end
        else:
            elements[1] = 0
            elements[2] = 0
            elements[3] = 0
            elements[4] = 0

        # Reconstruct the result string while maintaining spaces
        result_string = '{: <12} {: <11} {: <11} {: <10} {: <10} {: <10} \n'.format(*elements)

        lines[nth_line - 1] = result_string

        with open(time_sim_path, 'w') as file:
            file.writelines(lines)

    # 改变参数
    def change_params(self, tpl_filename: str, params: Dict[str, Dict]):
        """

        Args:
            tpl_filename: template file name, for example, "soils.sol.tpl"
                tpl文件里的参数需要用#key#来定义，例如 #awc#, 则 params 里用{“awc”: 0.2}
                这样来定义。
            params: dict[keys: values]用values替换keys,用#keys#定义需要替换的参数

        Returns: None

        """
        # read all file, line by line
        new_filename = tpl_filename.rsplit(".", 1)[0]
        tpl_path = self.root_folder / tpl_filename
        new_path = self.root_folder / new_filename
        with open(tpl_path) as file:
            lines = file.readlines()
            new_lines = "".join(lines)
            for k, v in params.items():
                new_lines = re.sub("#" + k + "#", str(v), new_lines)
        with open(new_path, "w") as file:
            file.write(new_lines)

    def _enable_disable_csv_print(self, enable: bool = True) -> None:
        """
        Enable or disable CSV print in the 'print.prt' file.

        Parameters:
        enable (bool, optional): True to enable CSV print, False to disable (default is True).

        Returns:
        None
        """

        # read
        nth_line = 7

        # time_sim_path = f"{self.root_folder}\\{'time.sim'}"
        print_prt_path = self.root_folder / 'print.prt'

        # Open the file in read mode and read its contents
        with open(print_prt_path, 'r') as file:
            lines = file.readlines()

        if enable:
            lines[nth_line - 1] = 'y' + lines[nth_line - 1][1:]
        else:
            lines[nth_line - 1] = 'n' + lines[nth_line - 1][1:]

        with open(print_prt_path, 'w') as file:
            file.writelines(lines)

    def enable_csv_print(self) -> None:
        """
        Enable CSV print in the 'print.prt' file.

        Returns:
        None
        """
        self._enable_disable_csv_print(enable=True)

    def disable_csv_print(self) -> None:
        """
        Disable CSV print in the 'print.prt' file.

        Returns:
        None
        """
        self._enable_disable_csv_print(enable=False)

    def register_file(self, filename: str, has_units: bool = False, index: Optional[str] = None,
                      usecols: Optional[List[str]] = None, filter_by: Dict[str, List[str]] = {}) -> FileReader:

        """
        Register a file to work with in the SWAT model.

        Parameters:
        filename (str): The name of the file to register.
        has_units (bool): Indicates if the file has units information (default is False).
        index (str, optional): The name of the index column (default is None).
        usecols (List[str], optional): A list of column names to read (default is None).
        filter_by (Dict[str, List[str]], optional): A dictionary of column names and values (list of str) to filter by (default is an empty dictionary).

        Returns:
        FileReader: A FileReader instance for the registered file.
        """

        file_path = os.path.join(self.root_folder, filename)
        return FileReader(file_path, has_units, index, usecols, filter_by)

    """
    if overwrite = True, content of dir folder will be deleted and txtinout folder will be copied there
    if overwrite = False, txtinout folder will be copied to a new folder inside dir
    """

    def copy_swat(self, dir: str = None, overwrite: bool = False) -> str:

        """
        Copy the SWAT model files to a specified directory.

        If 'overwrite' is True, the content of the 'dir' folder will be deleted, and the 'txtinout' folder will be copied there.
        If 'overwrite' is False, the 'txtinout' folder will be copied to a new folder inside 'dir'.

        Parameters:
        dir (str, optional): The target directory where the SWAT model files will be copied.
        overwrite (bool, optional): If True, overwrite the content of 'dir'; if False, create a new folder (default is False).

        Returns:
        str: The path to the directory where the SWAT model files were copied.
        """

        # if dir is None or dir is a folder and overwrite is False, create a new folder using mkdtemp
        if (dir is None) or (not overwrite and dir is not None):

            try:
                temp_folder_path = tempfile.mkdtemp(dir=dir)
            except FileNotFoundError:
                os.makedirs(dir, exist_ok=True)
                temp_folder_path = tempfile.mkdtemp(dir=dir)

        # if dir is a folder and overwrite is True, delete all contents
        elif overwrite:

            if os.path.isdir(dir):

                temp_folder_path = dir

                # delete all files in dir
                for file in os.listdir(dir):
                    file_path = os.path.join(dir, file)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        print(e)

            else:  # if overwrite and dir is not a folder, create dir anyway
                os.makedirs(dir, exist_ok=True)
                temp_folder_path = dir

        # check if dir does not exist
        elif not os.path.isdir(dir):
            # check if dir is a file
            if os.path.isfile(dir):
                raise TypeError("dir must be a folder")

            # create dir
            os.makedirs(dir, exist_ok=True)
            temp_folder_path = dir

        else:
            raise TypeError("option not recognized")

        # Get the list of files in the source folder
        source_folder = self.root_folder
        files = os.listdir(source_folder)

        # Exclude files with the specified suffix and copy the remaining files
        for file in files:
            if not file.endswith('_aa.txt') and not file.endswith('_aa.csv') and not file.endswith(
                    '_yr.txt') and not file.endswith('_yr.csv') and not file.endswith('_day.txt') and not file.endswith(
                    '_day.csv') and not file.endswith('_mon.csv') and not file.endswith('_mon.txt'):
                source_file = os.path.join(source_folder, file)
                destination_file = os.path.join(temp_folder_path, file)

                shutil.copy2(source_file, destination_file)

        return temp_folder_path

    def _run_swat(self, show_output: bool = True) -> None:
        """
        Run the SWAT simulation.

        Parameters:
        show_output (bool, optional): If True, print the simulation output; if False, suppress output (default is True).

        Returns:
        None
        """

        # Run siumulation
        swat_exe_path = self.swat_exe_path

        os.chdir(self.root_folder)

        with subprocess.Popen(swat_exe_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            # Read and print the output while it's being produced
            while True:
                # Read a line of output
                raw_output = process.stdout.readline()

                # Check if the output is empty and the subprocess has finished
                if raw_output == b'' and process.poll() is not None:
                    break

                # Decode the output using 'latin-1' encoding
                try:
                    output = raw_output.decode('latin-1').strip()
                except UnicodeDecodeError:
                    # Handle decoding errors here (e.g., skip or replace invalid characters)
                    continue

                # Print the decoded output if needed
                if output and show_output:
                    print(output)

    """
    params --> {filename: (id_col, [(id, col, value)])}
    """

    def run_swat(self,
                 params: Dict[str, Tuple[str, List[Tuple[str, str, int]]]] = {},
                 tpl_params: Dict[str, Dict] = {},
                 show_output: bool = True) -> str:
        """
        Run the SWAT simulation with modified input parameters.

        Parameters:
        params (Dict[str, Tuple[str, List[Tuple[str, str, int]]], optional): A dictionary containing modifications to input files. Format: {filename: (id_col, [(id, col, value)])}.
        tpl_file (List[str], optional): A list of tpl filenames
        tpl_params: List of dictionaries containing #keys# and values
        show_output (bool, optional): If True, print the simulation output; if False, suppress output (default is True).

        Returns:
        str: The path to the directory where the SWAT simulation was executed.
        """

        aux_txtinout = TxtinoutReader(self.root_folder)

        # Modify files for simulation
        for filename, file_params in params.items():

            id_col, file_mods = file_params

            # get file
            file = aux_txtinout.register_file(filename, has_units=False, index=id_col)

            # for each col_name in file_params
            for id, col_name, value in file_mods:  # if id is not given, value will be applied to all rows
                if id is None:
                    file.df[col_name] = value
                else:
                    file.df.loc[id, col_name] = value

            # store file
            file.overwrite_file()

        if tpl_params:
            for tpl_file, tpl_par in tpl_params.items():
                self.change_params(tpl_file, tpl_par)

        beginning = datetime.datetime.now()

        # run simulation
        # print(f'Simulation started at {beginning.strftime("%H:%M:%S")}. Stored at {str(self.root_folder)}.')
        aux_txtinout._run_swat(show_output=show_output)
        end = datetime.datetime.now()
        td = end - beginning

        return self.root_folder

    def run_swat_star(self, args: Tuple[Dict[str, Tuple[str, List[Tuple[str, str, int]]]], bool]) -> str:
        """
        Run the SWAT simulation with modified input parameters using arguments provided as a tuple.

        Parameters:
        args (Tuple[Dict[str, Tuple[str, List[Tuple[str, str, int]]], bool]): A tuple containing simulation parameters.
        The first element is a dictionary with input parameter modifications, the second element is a boolean to show output.

        Returns:
        str: The path to the directory where the SWAT simulation was executed.
        """
        return self.run_swat(*args)

    def copy_and_run(self,
                     dir: str,
                     overwrite: bool = False,
                     params: Dict[str, Tuple[str, List[Tuple[str, str, int]]]] = {},
                     tpl_params: Dict[str, Dict] ={},
                     show_output: bool = True) -> str:

        """
        Copy the SWAT model files to a specified directory, modify input parameters, and run the simulation.

        Parameters:
        dir (str): The target directory where the SWAT model files will be copied.
        overwrite (bool, optional): If True, overwrite the content of 'dir'; if False, create a new folder (default is False).
        params (Dict[str, Tuple[str, List[Tuple[str, str, int]]], optional): A dictionary containing modifications to input files.
        Format: {filename: (id_col, [(id, col, value)])}.
        show_output (bool, optional): If True, print the simulation output; if False, suppress output (default is True).

        Returns:
        str: The path to the directory where the SWAT simulation was executed.
        """

        tmp_path = self.copy_swat(dir=dir, overwrite=overwrite)
        reader = TxtinoutReader(tmp_path)
        return reader.run_swat(params, tpl_params, show_output=show_output)

    def copy_and_run_star(self, args: Tuple[str, bool, Dict[str, Tuple[str, List[Tuple[str, str, int]]]], bool]) -> str:
        """
        Copy the SWAT model files to a specified directory, modify input parameters, and run the simulation using arguments provided as a tuple.

        Parameters:
        args (Tuple[str, bool, Dict[str, Tuple[str, List[Tuple[str, str, int]]], bool]): A tuple containing simulation parameters.
        The first element is the target directory, the second element is a boolean to overwrite content, and the third element is a dictionary with input parameter modifications and a boolean to show output.

        Returns:
        str: The path to the directory where the SWAT simulation was executed.
        """
        return self.copy_and_run(*args)

    """
    params --> [{filename: (id_col, [(id, col, value)])}]
    """

    def run_parallel_swat(self,
                          params: List[Dict[str, Tuple[str, List[Tuple[str, str, int]]]]],
                          n_workers: int = 1,
                          dir: str = None,
                          client: Optional[dask.distributed.Client] = None) -> List[str]:

        """
        Run SWAT simulations in parallel with modified input parameters.

        Parameters:
        params (List[Dict[str, Tuple[str, List[Tuple[str, str, int]]]]): A list of dictionaries containing modifications to input files.
        Format: [{filename: (id_col, [(id, col, value)])}].
        n_workers (int, optional): The number of parallel workers to use (default is 1).
        dir (str, optional): The target directory where the SWAT model files will be copied (default is None).
        client (dask.distributed.Client, optional): A Dask client for parallel execution (default is None).

        Returns:
        List[str]: A list of paths to the directories where the SWAT simulations were executed.
        """

        max_treads = multiprocessing.cpu_count()
        threads = max(min(n_workers, max_treads), 1)

        if client is None:

            results_ret = []

            for i in tqdm.tqdm(range(len(params))):
                results_ret.append(self.copy_and_run(dir=dir,
                                                     overwrite=False,
                                                     params=params[i],
                                                     show_output=False))

            return results_ret

        else:

            items = [[dir, False, params[i], False] for i in range(len(params))]

            items = [[dir, False, params[i], False] for i in range(len(params))]

            futures = client.map(self.copy_and_run_star, items)
            results = client.gather(futures)

            return results


if __name__ == "__main__":
    reader = TxtinoutReader("E:\\4_CodeLearn\\Python\\pySWATPlus\\pySWATPlus\\TxtInOut")
    swat_params = {"hydrology.hyd": ("name", [
        (None, "esco", 0.8),
        (None, "epco", 0.8),
    ],
                                     )
                   }
    tpl_params = {"lum.dtl.tpl": {"fert_amount": 60},
                  "soils.sol.tpl": {"awc": 0.555}
                  }
    reader.copy_and_run("E:\\4_CodeLearn\\Python\\pySWATPlus\\pySWATPlus\\copy", params=swat_params, show_output=True)
