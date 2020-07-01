import os
import logging
from datetime import datetime, timedelta

import colorama

from wa.framework.configuration.core import Status
from wa import Command, settings
from wa.framework.output import RunOutput, discover_wa_outputs
from wa.framework.exception import NotFoundError
from wa.utils.terminalsize import get_terminal_size
from wa.utils.doc import format_column
from wa.utils.log import COLOR_MAP, RESET_COLOR

class StatusCommand(Command):

    name = 'runstatus'
    description = '''
    Monitor ongoing runs and provide information on their progress.

    '''

    def initialize(self, context):
        self.parser.add_argument('-d', '--directory',
                                 help='''
                                 Specify the WA output path. runstatus will
                                 otherwise attempt to discover output
                                 directories in the current directory.
                                 ''')

    def execute(self, config, args):
        if args.directory:
            output_path = args.directory
            run_output = RunOutput(output_path)
        else:
            possible_outputs = list(discover_wa_outputs(os.getcwd()))
            num_paths = len(possible_outputs)

            if num_paths > 1:
                print('More than one possible output directory found,'
                      ' please choose a path from the following:'
                      )

                for i in range(num_paths):
                    print(f"{i}: {possible_outputs[i].basepath}")

                while True:
                    try:
                        select = int(input())
                    except ValueError:
                        print(f"Please select number from "
                              f"{[x for x in range(num_paths)]}"
                              )
                        continue

                    if select not in range(num_paths):
                        print(f"Please select number from "
                              f"{[x for x in range(num_paths)]}"
                              )
                        continue
                    else:
                        break

                run_output = possible_outputs[select]

            else:
                run_output = possible_outputs[0]

        rs = RunMonitor(run_output)
        print(rs.generate_output(args.verbose))


class RunMonitor:

    @property
    def elapsed_time(self):
        if self._elapsed is None:
            if self.ro.info.duration is None:
                self._elapsed = datetime.utcnow() - self.ro.info.start_time
            else:
                self._elapsed = self.ro.info.duration
        return self._elapsed

    @property
    def job_outputs(self):
        if self._job_outputs is None:
            self._job_outputs = {
                (j_o.id, j_o.label, j_o.iteration): j_o for j_o in self.ro.jobs
            }
        return self._job_outputs

    @property
    def projected_duration(self):
        elapsed = self.elapsed_time.total_seconds()
        proj = timedelta(seconds=elapsed * (len(self.jobs) / len(self.segmented['finished'])))
        return proj - self.elapsed_time

    def __init__(self, ro):
        self.ro = ro
        self._elapsed = None
        self._p_duration = None
        self._job_outputs = None
        self._termwidth = None
        self.formatter = _simple_formatter()
        self.get_data()

    def get_data(self):
        self.jobs = [state for label_id, state in self.ro.state.jobs.items()]
        rc = self.ro._combined_config.run_config
        self.segmented = segment_jobs_by_state(self.jobs,
                                                rc.max_retries,
                                                rc.retry_on_status
                                                )

    def generate_run_header(self):
        info = self.ro.info
        
        header = ('\n=========================\n'
                  'Run Info'
                  '\n=========================\n\n'
                  )
        header += "UUID: {}\n".format(info.uuid)
        if info.run_name:
            header += "Run name: {}\n".format(info.run_name)
        if info.project:
            header += "Project: {}\n".format(info.project)
        if info.project_stage:
            header += "Project stage: {}\n".format(info.project_stage)

        if info.start_time:
            duration = _seconds_as_smh(self.elapsed_time.total_seconds())
            header += ("Start time: {}\n"
                       "Duration: {:02}:{:02}:{:02}\n"
                       ).format(info.start_time,
                                duration[2], duration[1], duration[0],
                                )
            if len(self.segmented['finished']) and not info.end_time:
                p_duration = _seconds_as_smh(self.projected_duration.total_seconds())
                header += "Projected time remaining: {:02}:{:02}:{:02}\n".format(
                    p_duration[2], p_duration[1], p_duration[0]
                )

            elif self.ro.info.end_time:
                header += f"End time: {info.end_time}\n"

        return header

    def generate_job_summary(self):
        total = len(self.jobs)
        num_fin = len(self.segmented['finished'])

        summary = ('\n=========================\n'
                   'Job Summary'
                   '\n=========================\n\n'
                   )
        summary += f'Total: {total}, Completed: {num_fin} ({(num_fin/total)*100}%)\n'

        job_list = []
        for run_state, jobs in ((k, v) for k, v in self.segmented.items() if v):
            if run_state == 'finished':
                end_states = {
                                Status.PARTIAL: 0, Status.FAILED: 0,
                                Status.ABORTED: 0, Status.OK: 0,
                                Status.SKIPPED: 0
                              }
                for job in jobs:
                    end_states[job.status] += 1

                for status, count in end_states.items():
                    if count:
                        job_list.append('{} {}'.format(
                            count,
                            self.formatter.highlight_keyword(status.name.lower())
                            )
                        )

            else:
                count = len(jobs)
                job_list.append('{} {}'.format(
                    count,
                    self.formatter.highlight_keyword(run_state)
                    )
                )

        summary = summary + ', '.join(job_list) + '\n'
        return summary

    def generate_job_detail(self):
        detail = ('\n=========================\n'
                  'Job Detail'
                  '\n=========================\n\n'
                  )

        for segment, jobstates in self.segmented.items():
            if jobstates:
                for job in jobstates:
                    detail += ('{} ({}) [{}]'
                               '{}, {}\n'
                               ).format(
                                   job.id,
                                   job.label,
                                   job.iteration,
                                   ' - ' + str(job.retries)if job.retries else '',
                                   self.formatter.highlight_keyword(str(job.status))
                                )
                    job_output = self.job_outputs[(job.id,job.label,job.iteration)]
                    
                    for event in job_output.events:
                        detail += self.formatter.fit_term_width(f'\t{event.summary}\n')
        return detail

    def generate_run_detail(self):
        detail = ('\n\n=========================\n'
                  'Run Events'
                  '\n=========================\n\n'
                  ) if self.ro.events else ''

        for event in self.ro.events:
            detail += f'{event.summary}\n'

        return detail

    def generate_output(self, verbose):
        output = self.generate_run_header()
        output += self.generate_job_summary()

        if verbose:
            output += self.generate_run_detail()
            output += self.generate_job_detail()

        return output


def _seconds_as_smh(seconds):
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return seconds, minutes, hours


def segment_jobs_by_state(jobstates, max_retries, retry_status):
    finished_states = [
            Status.PARTIAL, Status.FAILED,
            Status.ABORTED, Status.OK, Status.SKIPPED
    ]

    segmented = {
        'finished': [], 'other': [], 'running': [],
        'pending': [], 'uninitialized': []
    }

    for jobstate in jobstates:
        if (jobstate.status in retry_status) and jobstate.retries < max_retries:
            segmented['running'].append(jobstate)
        elif jobstate.status in finished_states:
            segmented['finished'].append(jobstate)
        elif jobstate.status == Status.RUNNING:
            segmented['running'].append(jobstate)
        elif jobstate.status == Status.PENDING:
            segmented['pending'].append(jobstate)
        elif jobstate.status == Status.NEW:
            segmented['uninitialized'].append(jobstate)
        else:
            segmented['other'].append(jobstate)

    return segmented


class _simple_formatter:
    color_map = {
        'running': COLOR_MAP[logging.INFO],
        'ok': colorama.Fore.WHITE,
        'partial': COLOR_MAP[logging.WARNING],
        'failed': COLOR_MAP[logging.CRITICAL],
        'aborted': COLOR_MAP[logging.ERROR],
        'skipped': colorama.Fore.WHITE,
        'pending': colorama.Fore.WHITE,
        'new': colorama.Fore.WHITE,
    }

    def __init__(self):
        self.termwidth = get_terminal_size()[0]
        self.color = settings.logging['color']

    def fit_term_width(self, text):
        text = text.expandtabs()
        if len(text) <= self.termwidth:
            return text
        else:
            return text[0:self.termwidth - 4] + " ...\n"

    def highlight_keyword(self, kw):
        if not self.color:
            return kw

        color = _simple_formatter.color_map[kw.lower()]
        return '{}{}{}'.format(color, kw, RESET_COLOR)
