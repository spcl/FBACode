
class Statistics:

    def __init__(self):
        self.correct_projects = 0
        self.incorrect_projects = 0
        self.unrecognized_projects = 0
        self.clone_time = 0
        self.build_time = 0

    def print_stats(self):
        print('Repository clone time: %f seconds' % self.clone_time)
        print('Repository build time: %f seconds' % self.build_time)
        print('Succesfull builds: %d' % self.correct_projects)
        print('Failed builds: %d' % self.incorrect_projects)
        print('Unrecognized builds: %d' % self.unrecognized_projects)

    def update(self, project):
        self.clone_time += project['source']['time']
        if 'build' in project:
            self.build_time += project['build']['time']

    def add_unrecognized_project(self):
        self.unrecognized_projects += 1

    def add_correct_project(self):
        self.correct_projects += 1

    def add_incorrect_project(self):
        self.incorrect_projects += 1
