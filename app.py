from flask import Flask, render_template, request, jsonify, send_file, session
import pandas as pd
import os
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    file_type = request.form.get('file_type')  # 'left' or 'right'
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    try:
        # Generate unique filename
        file_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{file_id}_{filename}")
        file.save(filepath)
        
        # Read file
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        
        # Store file info in session
        if 'files' not in session:
            session['files'] = {}
        
        session['files'][file_type] = {
            'filepath': filepath,
            'filename': filename,
            'file_id': file_id
        }
        session.modified = True
        
        # Return file info
        return jsonify({
            'success': True,
            'filename': filename,
            'columns': list(df.columns),
            'rows': len(df),
            'preview': df.head(3).to_dict('records')
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to read file: {str(e)}'}), 400

@app.route('/get_columns', methods=['GET'])
def get_columns():
    """Get columns from both uploaded files"""
    if 'files' not in session or 'left' not in session['files'] or 'right' not in session['files']:
        return jsonify({'error': 'Please upload both files first'}), 400
    
    try:
        # Read both files
        left_file = session['files']['left']['filepath']
        right_file = session['files']['right']['filepath']
        
        if left_file.endswith('.csv'):
            df_left = pd.read_csv(left_file)
        else:
            df_left = pd.read_excel(left_file)
        
        if right_file.endswith('.csv'):
            df_right = pd.read_csv(right_file)
        else:
            df_right = pd.read_excel(right_file)
        
        # Find common columns
        common_cols = list(set(df_left.columns) & set(df_right.columns))
        
        return jsonify({
            'success': True,
            'left_columns': list(df_left.columns),
            'right_columns': list(df_right.columns),
            'common_columns': common_cols
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to read columns: {str(e)}'}), 400

@app.route('/join', methods=['POST'])
def join_files():
    """Perform the join operation"""
    if 'files' not in session or 'left' not in session['files'] or 'right' not in session['files']:
        return jsonify({'error': 'Please upload both files first'}), 400
    
    try:
        data = request.json
        left_columns = data.get('left_columns', [])
        right_columns = data.get('right_columns', [])
        join_type = data.get('join_type', 'inner')
        
        if not left_columns or not right_columns:
            return jsonify({'error': 'Please select columns to join on'}), 400
        
        if len(left_columns) != len(right_columns):
            return jsonify({'error': 'Number of selected columns must match'}), 400
        
        # Read both files
        left_file = session['files']['left']['filepath']
        right_file = session['files']['right']['filepath']
        
        if left_file.endswith('.csv'):
            df_left = pd.read_csv(left_file)
        else:
            df_left = pd.read_excel(left_file)
        
        if right_file.endswith('.csv'):
            df_right = pd.read_csv(right_file)
        else:
            df_right = pd.read_excel(right_file)
        
        # Perform join
        df_joined = pd.merge(
            df_left, 
            df_right, 
            left_on=left_columns, 
            right_on=right_columns, 
            how=join_type
        )
        
        if df_joined.empty:
            return jsonify({'warning': 'Join returned no rows', 'columns': [], 'rows': 0})
        
        # Save joined file temporarily
        joined_id = str(uuid.uuid4())
        joined_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{joined_id}_joined.xlsx")
        df_joined.to_excel(joined_filepath, index=False)
        
        session['joined_file'] = {
            'filepath': joined_filepath,
            'file_id': joined_id
        }
        session.modified = True
        
        return jsonify({
            'success': True,
            'columns': list(df_joined.columns),
            'rows': len(df_joined),
            'preview': df_joined.head(5).to_dict('records')
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to join files: {str(e)}'}), 400

@app.route('/download', methods=['POST'])
def download_file():
    """Download the final Excel file with selected columns"""
    if 'joined_file' not in session:
        return jsonify({'error': 'No joined file available'}), 400
    
    try:
        data = request.json
        selected_columns = data.get('selected_columns', [])
        
        if not selected_columns:
            return jsonify({'error': 'Please select at least one column'}), 400
        
        # Read joined file
        joined_filepath = session['joined_file']['filepath']
        df_joined = pd.read_excel(joined_filepath)
        
        # Select only the chosen columns
        df_final = df_joined[selected_columns]
        
        # Save final file
        final_id = str(uuid.uuid4())
        final_filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{final_id}_final.xlsx")
        df_final.to_excel(final_filepath, index=False)
        
        return send_file(
            final_filepath,
            as_attachment=True,
            download_name='joined_output.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    except Exception as e:
        return jsonify({'error': f'Failed to create download: {str(e)}'}), 400

@app.route('/reset', methods=['POST'])
def reset():
    """Reset the session and clean up files"""
    if 'files' in session:
        for file_type in session['files']:
            filepath = session['files'][file_type].get('filepath')
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
    
    if 'joined_file' in session:
        filepath = session['joined_file'].get('filepath')
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    
    session.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")