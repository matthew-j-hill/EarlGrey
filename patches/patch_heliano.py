import sys
src, dst = sys.argv[1], sys.argv[2]
lines = open(src).read().split('\n')
# lines 836-840 (1-based) = indices 835-839: the stock blastn Popen call + wait
old = lines[835:840]
assert old[0].strip() == 'blastn_pro = subprocess.Popen(', old[0]
assert old[1].strip().startswith("['blastn', '-db', self.genomedb, '-query', query_file, '-num_threads', str(self.process_num),"), old[1]
assert old[3].strip().endswith("'-out', blastn_opt])"), old[3]
assert old[4].strip() == 'blastn_pro.wait()', old[4]
new = '''        ## Patched: if HELIANO_BLAST_CHUNK_SEQS is set, split the query into small contiguous chunks and run them
        ## through a pool of HELIANO_BLAST_JOBS concurrent blastn workers (HELIANO_BLAST_THREADS threads each).
        ## The pool size is re-read from the file HELIANO_BLAST_JOBS_FILE (if it exists) before each launch, so it
        ## can be changed while running. Outputs are concatenated in chunk order = stock query-sorted table.
        blast_args = ['-db', self.genomedb,
                      '-max_target_seqs', '999999999', '-evalue', str(self.evalue_blastn), '-task', 'blastn-short',
                      '-outfmt', '6 qseqid sseqid pident qstart qend sstart send evalue qlen bitscore']
        chunk_seqs = int(os.environ.get('HELIANO_BLAST_CHUNK_SEQS', '0'))
        if chunk_seqs <= 0:
            blastn_pro = subprocess.Popen(['blastn'] + blast_args + ['-num_threads', str(self.process_num), '-query', query_file, '-out', blastn_opt])
            blastn_pro.wait()
        else:
            import shutil, time
            nthr = os.environ.get('HELIANO_BLAST_THREADS', '1')
            njobs_default = int(os.environ.get('HELIANO_BLAST_JOBS', '8'))
            jobs_file = os.environ.get('HELIANO_BLAST_JOBS_FILE', '')
            def njobs():
                try:
                    with open(jobs_file) as J:
                        return max(0, int(J.read().strip()))
                except (OSError, ValueError):
                    return njobs_default
            recs = []
            with open(query_file) as F:
                for line in F:
                    if line.startswith('>'):
                        recs.append([line])
                    elif recs:
                        recs[-1].append(line)
            parts = []
            for i in range(0, len(recs), chunk_seqs):
                qf = '%s.chunk%05d' % (query_file, i // chunk_seqs)
                with open(qf, 'w') as O:
                    for r in recs[i:i + chunk_seqs]:
                        O.writelines(r)
                parts.append(qf)
            sys.stdout.write('blastn: %s: %d queries in %d chunks; %d workers x %s threads\\n' % (os.path.basename(query_file), len(recs), len(parts), njobs(), nthr))
            pending = list(parts)
            running = {}
            done = 0
            failed = []
            t0 = time.time()
            while pending or running:
                while pending and len(running) < njobs():
                    qf = pending.pop(0)
                    running[qf] = subprocess.Popen(['blastn'] + blast_args + ['-num_threads', nthr, '-query', qf, '-out', qf + '.tbl'])
                for qf, p in list(running.items()):
                    rc = p.poll()
                    if rc is not None:
                        del running[qf]
                        done += 1
                        if rc != 0:
                            failed.append('%s (exit %d)' % (qf, rc))
                        if done % 10 == 0 or done == len(parts):
                            sys.stdout.write('blastn: %d/%d chunks done, %d running, %.0f min elapsed\\n' % (done, len(parts), len(running), (time.time() - t0) / 60))
                time.sleep(2)
            if failed:
                sys.stderr.write('ERROR: blastn failed for chunk(s): %s\\n' % ', '.join(failed))
                sys.exit(1)
            with open(blastn_opt, 'wb') as O:
                for qf in parts:
                    with open(qf + '.tbl', 'rb') as I:
                        shutil.copyfileobj(I, O, 16 * 1024 * 1024)
                    os.remove(qf + '.tbl')
                    os.remove(qf)'''.split('\n')
lines[835:840] = new
open(dst, 'w').write('\n'.join(lines))
print('patched OK')
