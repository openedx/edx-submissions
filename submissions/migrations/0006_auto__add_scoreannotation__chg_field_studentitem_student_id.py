# -*- coding: utf-8 -*-
from south.utils import datetime_utils as datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models


class Migration(SchemaMigration):

    def forwards(self, orm):
        # Adding model 'ScoreAnnotation'
        db.create_table('submissions_scoreannotation', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('score', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['submissions.Score'])),
            ('annotation_type', self.gf('django.db.models.fields.CharField')(max_length=255, db_index=True)),
            ('creator', self.gf('submissions.models.AnonymizedUserIDField')(max_length=255, db_index=True)),
            ('reason', self.gf('django.db.models.fields.TextField')()),
        ))
        db.send_create_signal('submissions', ['ScoreAnnotation'])


        # Changing field 'StudentItem.student_id'
        db.alter_column('submissions_studentitem', 'student_id', self.gf('submissions.models.AnonymizedUserIDField')(max_length=255))

    def backwards(self, orm):
        # Deleting model 'ScoreAnnotation'
        db.delete_table('submissions_scoreannotation')


        # Changing field 'StudentItem.student_id'
        db.alter_column('submissions_studentitem', 'student_id', self.gf('django.db.models.fields.CharField')(max_length=255))

    models = {
        'submissions.score': {
            'Meta': {'object_name': 'Score'},
            'created_at': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'points_earned': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0'}),
            'points_possible': ('django.db.models.fields.PositiveIntegerField', [], {'default': '0'}),
            'reset': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'student_item': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['submissions.StudentItem']"}),
            'submission': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['submissions.Submission']", 'null': 'True'})
        },
        'submissions.scoreannotation': {
            'Meta': {'object_name': 'ScoreAnnotation'},
            'annotation_type': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'creator': ('submissions.models.AnonymizedUserIDField', [], {'max_length': '255', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'reason': ('django.db.models.fields.TextField', [], {}),
            'score': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['submissions.Score']"})
        },
        'submissions.scoresummary': {
            'Meta': {'object_name': 'ScoreSummary'},
            'highest': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'+'", 'to': "orm['submissions.Score']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'latest': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'+'", 'to': "orm['submissions.Score']"}),
            'student_item': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['submissions.StudentItem']", 'unique': 'True'})
        },
        'submissions.studentitem': {
            'Meta': {'unique_together': "(('course_id', 'student_id', 'item_id'),)", 'object_name': 'StudentItem'},
            'course_id': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'item_id': ('django.db.models.fields.CharField', [], {'max_length': '255', 'db_index': 'True'}),
            'item_type': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'student_id': ('submissions.models.AnonymizedUserIDField', [], {'max_length': '255', 'db_index': 'True'})
        },
        'submissions.submission': {
            'Meta': {'ordering': "['-submitted_at', '-id']", 'object_name': 'Submission'},
            'answer': ('jsonfield.fields.JSONField', [], {'db_column': "'raw_answer'", 'blank': 'True'}),
            'attempt_number': ('django.db.models.fields.PositiveIntegerField', [], {}),
            'created_at': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now', 'db_index': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'student_item': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['submissions.StudentItem']"}),
            'submitted_at': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now', 'db_index': 'True'}),
            'uuid': ('django.db.models.fields.CharField', [], {'db_index': 'True', 'max_length': '36', 'blank': 'True'})
        }
    }

    complete_apps = ['submissions']